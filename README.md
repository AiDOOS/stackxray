========================================================================
 StackXray  -  Find your best "make it an AI agent" opportunities
========================================================================

WHAT IT DOES
StackXray scans a folder of code on your computer and gives you a clean,
one-page report of the capabilities that are the strongest candidates to
rebuild as AI agents -- ranked, with the reason for each.

Everything runs on your own computer. Your code never leaves it.


------------------------------------------------------------------------
 STEP 1  -  Install Python  (one time)
------------------------------------------------------------------------
- A Windows PC.
- Python 3.11 or newer. If you are not sure you have it:
    1. Go to   https://www.python.org/downloads
    2. Download and run the installer.
    3. IMPORTANT: on the FIRST screen, tick the box
       "Add Python to PATH".
    4. Click "Install Now". That's it.


------------------------------------------------------------------------
 STEP 2  -  Unzip StackXray  (one time)
------------------------------------------------------------------------
1. Right-click this ZIP file and choose  "Extract All..."
2. Pick a folder to extract to, for example   C:\StackXray
3. Click Extract.

You now have a folder (e.g. C:\StackXray) with StackXray.bat and
API-KEY.txt inside it.


------------------------------------------------------------------------
 STEP 3  -  Add your AI key  (REQUIRED)
------------------------------------------------------------------------
StackXray reads your code with an AI model to give specific, validated
findings. The local version uses YOUR key (that is what keeps your code on
this machine - nothing is ever sent to AiDOOS). You must add one before
you run it:

1. Open the file  API-KEY.txt  (it sits next to StackXray.bat).
2. Paste in ONE of these and save:

     Claude (recommended):  ANTHROPIC_API_KEY=your-key-here
     OpenAI:                OPENAI_API_KEY=your-key-here

3. Save and close the file.

Your key and your code stay on this computer. The key is used only to call
your chosen AI provider directly from here, and is never sent to AiDOOS.
If you run StackXray without a key it will stop and ask you for one.


------------------------------------------------------------------------
 STEP 4  -  Run  (every time)
------------------------------------------------------------------------
1. Open the folder where you extracted it (e.g. C:\StackXray).
2. Double-click   StackXray.bat
3. A small black window opens, and then a page opens in your web browser.
4. In that page, type (or paste) the full path to the folder of code you
   want to scan -- for example   C:\my-project   -- or a GitHub URL, and
   click "Run scan".
5. Wait a few seconds. The report appears right there in your browser.

To scan another folder, just go back and enter a different path.
When you are finished, close the small black window to stop.


------------------------------------------------------------------------
 TROUBLE?
------------------------------------------------------------------------
- "Python was not found"  ->  Python isn't installed, or the
  "Add Python to PATH" box wasn't ticked. Re-install Python from
  python.org and tick that box.
- Running a scan needs internet (to reach your AI provider) and your key in API-KEY.txt.
- Nothing to sign in to. No accounts.

Questions?  Reply to the email this came from and we'll help.
========================================================================
