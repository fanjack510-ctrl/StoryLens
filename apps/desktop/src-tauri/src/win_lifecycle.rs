//! Windows helpers for sidecar process ownership (Job Object + PID discovery).
#![cfg(windows)]

use std::collections::{HashMap, HashSet, VecDeque};
use std::mem::{size_of, zeroed};
use std::os::windows::io::RawHandle;
use std::ptr;

use windows_sys::Win32::Foundation::{
    CloseHandle, FALSE, HANDLE, INVALID_HANDLE_VALUE, WAIT_OBJECT_0,
};
use windows_sys::Win32::NetworkManagement::IpHelper::{
    GetExtendedTcpTable, MIB_TCP_STATE_LISTEN, TCP_TABLE_OWNER_PID_LISTENER,
};
use windows_sys::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Process32FirstW, Process32NextW, PROCESSENTRY32W,
    TH32CS_SNAPPROCESS,
};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows_sys::Win32::System::Threading::{
    OpenProcess, TerminateProcess, WaitForSingleObject, PROCESS_QUERY_LIMITED_INFORMATION,
    PROCESS_TERMINATE,
};

pub struct JobHandle {
    handle: HANDLE,
}

unsafe impl Send for JobHandle {}

impl JobHandle {
    pub fn create() -> Option<Self> {
        unsafe {
            let handle = CreateJobObjectW(ptr::null(), ptr::null());
            if handle.is_null() {
                return None;
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &mut info as *mut _ as *mut _,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok == FALSE {
                let _ = CloseHandle(handle);
                return None;
            }
            Some(Self { handle })
        }
    }

    pub fn assign_raw_handle(&self, process: RawHandle) -> bool {
        unsafe {
            let ok = AssignProcessToJobObject(self.handle, process as HANDLE);
            ok != FALSE
        }
    }

    pub fn assign_pid(&self, pid: u32) -> bool {
        unsafe {
            let proc = OpenProcess(
                PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION,
                FALSE,
                pid,
            );
            if proc.is_null() {
                return false;
            }
            let ok = AssignProcessToJobObject(self.handle, proc);
            let _ = CloseHandle(proc);
            ok != FALSE
        }
    }
}

impl Drop for JobHandle {
    fn drop(&mut self) {
        unsafe {
            if !self.handle.is_null() {
                let _ = CloseHandle(self.handle);
            }
        }
    }
}

pub fn pids_for_executable_path(normalized_key: &str) -> Vec<u32> {
    let mut out = Vec::new();
    for (pid, path) in enumerate_process_paths() {
        let key = path.trim_end_matches(['\\', '/']).to_lowercase();
        if key == normalized_key {
            out.push(pid);
        }
    }
    out.sort_unstable();
    out.dedup();
    out
}

fn enumerate_process_paths() -> Vec<(u32, String)> {
    let mut result = Vec::new();
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, and_zero());
        if snap == INVALID_HANDLE_VALUE {
            return result;
        }
        let mut entry: PROCESSENTRY32W = zeroed();
        entry.dwSize = size_of::<PROCESSENTRY32W>() as u32;
        if Process32FirstW(snap, &mut entry) != 0 {
            loop {
                let pid = entry.th32ProcessID;
                if let Some(path) = query_process_image_path(pid) {
                    result.push((pid, path));
                }
                if Process32NextW(snap, &mut entry) == 0 {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    result
}

fn and_zero() -> u32 {
    0
}

fn query_process_image_path(pid: u32) -> Option<String> {
    unsafe {
        let proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if proc.is_null() {
            return None;
        }
        let mut buf = [0u16; 1024];
        let mut size = buf.len() as u32;
        extern "system" {
            fn QueryFullProcessImageNameW(
                h: HANDLE,
                flags: u32,
                exe: *mut u16,
                size: *mut u32,
            ) -> i32;
        }
        let ok = QueryFullProcessImageNameW(proc, 0, buf.as_mut_ptr(), &mut size);
        let _ = CloseHandle(proc);
        if ok == 0 || size == 0 {
            return None;
        }
        Some(String::from_utf16_lossy(&buf[..size as usize]))
    }
}

pub fn descendant_pids(root: u32) -> Vec<u32> {
    let mut parent_map: HashMap<u32, Vec<u32>> = HashMap::new();
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if snap == INVALID_HANDLE_VALUE {
            return Vec::new();
        }
        let mut entry: PROCESSENTRY32W = zeroed();
        entry.dwSize = size_of::<PROCESSENTRY32W>() as u32;
        if Process32FirstW(snap, &mut entry) != 0 {
            loop {
                parent_map
                    .entry(entry.th32ParentProcessID)
                    .or_default()
                    .push(entry.th32ProcessID);
                if Process32NextW(snap, &mut entry) == 0 {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    let mut found = Vec::new();
    let mut seen = HashSet::new();
    let mut q = VecDeque::new();
    q.push_back(root);
    seen.insert(root);
    while let Some(cur) = q.pop_front() {
        if let Some(children) = parent_map.get(&cur) {
            for &cid in children {
                if seen.insert(cid) {
                    found.push(cid);
                    q.push_back(cid);
                }
            }
        }
    }
    found
}

pub fn terminate_pid(pid: u32) {
    unsafe {
        let proc = OpenProcess(PROCESS_TERMINATE, FALSE, pid);
        if proc.is_null() {
            return;
        }
        let _ = TerminateProcess(proc, 1);
        let _ = WaitForSingleObject(proc, 2000);
        let _ = CloseHandle(proc);
    }
}

pub fn pid_alive(pid: u32) -> bool {
    unsafe {
        let proc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if proc.is_null() {
            return false;
        }
        let status = WaitForSingleObject(proc, 0);
        let _ = CloseHandle(proc);
        status != WAIT_OBJECT_0
    }
}

#[repr(C)]
struct MibTcpRowOwnerPid {
    state: u32,
    local_addr: u32,
    local_port: u32,
    remote_addr: u32,
    remote_port: u32,
    owning_pid: u32,
}

pub fn tcp_listen_owner(port: u16) -> Option<u32> {
    unsafe {
        let mut size: u32 = 0;
        let _ = GetExtendedTcpTable(
            ptr::null_mut(),
            &mut size,
            FALSE,
            2, // AF_INET
            TCP_TABLE_OWNER_PID_LISTENER,
            0,
        );
        if size == 0 {
            return None;
        }
        let mut buf = vec![0u8; size as usize];
        let status = GetExtendedTcpTable(
            buf.as_mut_ptr() as *mut _,
            &mut size,
            FALSE,
            2,
            TCP_TABLE_OWNER_PID_LISTENER,
            0,
        );
        if status != 0 {
            return None;
        }
        if size < 4 {
            return None;
        }
        let num = u32::from_le_bytes([buf[0], buf[1], buf[2], buf[3]]) as usize;
        let row_size = size_of::<MibTcpRowOwnerPid>();
        let want = u32::from(port);
        for i in 0..num {
            let off = 4 + i * row_size;
            if off + row_size > buf.len() {
                break;
            }
            let row = &*(buf.as_ptr().add(off) as *const MibTcpRowOwnerPid);
            if row.state != MIB_TCP_STATE_LISTEN as u32 {
                continue;
            }
            let local_port = ((row.local_port & 0xFF) << 8) | ((row.local_port >> 8) & 0xFF);
            if local_port == want {
                return Some(row.owning_pid);
            }
        }
        None
    }
}
