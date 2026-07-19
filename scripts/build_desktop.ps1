$ErrorActionPreference='Stop';Push-Location apps/desktop;try{& npm.cmd run typecheck;if($LASTEXITCODE){exit $LASTEXITCODE};& npm.cmd run build;exit $LASTEXITCODE}finally{Pop-Location}
