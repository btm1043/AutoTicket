# Building the separate WebView2 version

The WebView2 spike lives in:

- `autoticket_webview2.cs`
- `autoticket_webview2.csproj`

It now includes `.msg` parsing through `MsgReader`, so dropped Outlook messages populate the JSON panel the same way the Python build does.

The automatic local Outlook Inbox subfolder queue is currently implemented in the Python/PyQt build only.
This WebView2 spike supports dropped `.msg` files, but it does not scan a running Outlook instance or maintain the `outlook_acted.json` ledger.

## Single EXE publish

Framework-dependent single EXE:

```powershell
.\publish_webview2.ps1
```

That produces:

```text
dist\autoticket-webview2-singleexe\AutoTicket.WebView2.exe
```

This is the smallest option and is currently measuring about `3.22 MB`, but target machines must already have:

- WebView2 Runtime
- .NET 8 Windows Desktop Runtime

Self-contained single EXE:

```powershell
.\publish_webview2.ps1 -Mode SelfContained
```

That produces:

```text
dist\autoticket-webview2-singleexe-selfcontained\AutoTicket.WebView2.exe
```

This is currently measuring about `156.52 MB`. It carries its own .NET runtime, but target machines still need WebView2 Runtime installed.

## Important limitation

WebView2 itself is not embedded in these EXEs. They rely on the machine's installed WebView2 Runtime.

If you need a build that runs on machines without WebView2 Runtime, you would need to ship a fixed-version WebView2 Runtime with the app, which stops being a single-file deployment.
