-- Greek OCR — drag-and-drop front end for greek_ocr.py
-- ギリシャ語OCR — greek_ocr.py をドラッグ＆ドロップで使うためのアプリ
--
-- Copyright (c) 2026 Masahiro Kitano. MIT License.
-- install.sh compiles this file into an app with osacompile.
-- install.sh がこのファイルから osacompile でアプリを作る。

property launcher : "~/GreekOCR/greek-ocr.sh"

on isJapanese()
	try
		return (user locale of (system info)) starts with "ja"
	on error
		return false
	end try
end isJapanese

on run
	if my isJapanese() then
		set thePrompt to "OCRするフォルダを選んでください（commandキーで複数選択可）"
	else
		set thePrompt to "Choose the folder(s) to process (hold Command to choose several)"
	end if
	set theFolders to choose folder with prompt thePrompt with multiple selections allowed
	processFolders(theFolders)
end run

on open theItems
	processFolders(theItems)
end open

on processFolders(theItems)
	set ja to my isJapanese()
	if ja then
		set appTitle to "ギリシャ語OCR"
		set dataMsg to "認識データを選んでください。" & return & return & "best版：精度優先（時間がかかります）" & return & "通常版：速度優先"
		set bCancel to "キャンセル"
		set bFast to "通常版"
		set bBest to "best版"
		set cDry to "下見のみ"
		set cRun to "OCR開始"
		set cForce to "強制OCR（ギリシャ語が化ける本用）"
		set listMsg to "選んだ " & (count of theItems) & " 個のフォルダをどうしますか？"
		set doneText to "処理が終わりました"
	else
		set appTitle to "Greek OCR"
		set dataMsg to "Choose the OCR data." & return & return & "Best: more accurate (slower)" & return & "Standard: faster"
		set bCancel to "Cancel"
		set bFast to "Standard"
		set bBest to "Best"
		set cDry to "Preview only"
		set cRun to "Start OCR"
		set cForce to "Forced OCR (for books whose Greek stays garbled)"
		set listMsg to "What should be done with the " & (count of theItems) & " folder(s)?"
		set doneText to "Finished"
	end if

	-- Messages of greek_ocr.py in the same language / スクリプトの表示言語もそろえる
	if ja then
		set langEnv to "GREEK_OCR_LANG=ja "
	else
		set langEnv to "GREEK_OCR_LANG=en "
	end if
	
	-- 1. OCR data / 認識データ
	set dataAns to button returned of (display dialog dataMsg buttons {bCancel, bFast, bBest} default button bBest cancel button bCancel with title appTitle)
	if dataAns is bFast then
		set dataFlag to " --fast"
	else
		set dataFlag to ""
	end if

	-- 2. What to do / 処理内容
	set picked to choose from list {cDry, cRun, cForce} with title appTitle & " (" & dataAns & ")" with prompt listMsg default items {cRun}
	if picked is false then return
	set ans to item 1 of picked

	set cmd to "clear"
	repeat with f in theItems
		set p to quoted form of (POSIX path of f)
		if ans is cDry then
			set cmd to cmd & "; " & langEnv & launcher & " " & p & " --dry-run" & dataFlag
		else if ans is cRun then
			set cmd to cmd & "; " & langEnv & "caffeinate -i nice -n 10 " & launcher & " " & p & dataFlag
		else
			set cmd to cmd & "; " & langEnv & "caffeinate -i nice -n 10 " & launcher & " " & p & " --force" & dataFlag
		end if
	end repeat
	set doneMsg to "display notification \"" & doneText & "\" with title \"" & appTitle & "\" sound name \"Glass\""
	set cmd to cmd & "; osascript -e " & quoted form of doneMsg
	tell application "Terminal"
		activate
		do script cmd
	end tell
end processFolders
