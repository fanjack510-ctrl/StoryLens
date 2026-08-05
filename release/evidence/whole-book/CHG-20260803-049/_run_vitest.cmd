@echo off
chcp 65001 >nul
cd /d D:\Dstorylens-wt-1.2.0-after-1.1.2\apps\desktop
set EV=D:\Dstorylens-wt-1.2.0-after-1.1.2\release\evidence\whole-book\CHG-20260803-049
echo START %DATE% %TIME% > "%EV%\DESKTOP_FULL_VITEST.txt"
npx vitest run > "%EV%\DESKTOP_FULL_VITEST.raw.txt" 2>&1
echo EXIT=%ERRORLEVEL%>> "%EV%\DESKTOP_FULL_VITEST.txt"
type "%EV%\DESKTOP_FULL_VITEST.raw.txt" >> "%EV%\DESKTOP_FULL_VITEST.txt"
echo END %DATE% %TIME%>> "%EV%\DESKTOP_FULL_VITEST.txt"
