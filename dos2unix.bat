for /f "tokens=* delims=" %%a in ('dir "D:\Workspace\Python\proxyscanner" /s /b') do (
"D:\Applications\dos2unix-7.4.1-win64\bin\dos2unix.exe" %%a
)