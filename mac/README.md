# Buzz for Mac

The dashboard in its own Mac window. The hub keeps running where it is; the
app only opens its URL. It adds a menu-bar icon, a Dock badge with the number
of agents that need you, and a notification when an agent starts needing you.

The badge and notifications need a hub whose dashboard includes
`web/src/native.js` (on master since this app was added). An older hub still
loads, without them.

## Build and install

On the Mac you need the Command Line Tools (`xcode-select --install`), Rust
from [rustup](https://rustup.rs), and Node.js 22 or newer. Xcode.app is not
needed. From this directory:

```sh
npm ci
npm run build
```

This makes `src-tauri/target/release/bundle/macos/Buzz.app`. Copy it to
`/Applications` (`ditto`, so the signature is kept). There is no DMG: its
Finder step needs Automation permission and fails from a plain terminal.

The app used to be called Agent Swarm. Its bundle id is unchanged, so
Buzz.app keeps the saved hub URL; delete the old `Agent Swarm.app`.

The build signs the whole app ad hoc (`signingIdentity: "-"` in
`tauri.conf.json`). macOS refuses notifications to an app whose bundle is not
signed. Ad-hoc signatures change on every build, so macOS may ask for
notification permission again after a rebuild.

A local build is not quarantined and opens directly. A copy downloaded from
elsewhere is blocked the first time; allow it in System Settings → Privacy &
Security → Open Anyway. Signing for other people needs an Apple developer
account; see [Tauri's guide](https://v2.tauri.app/distribute/sign/macos/).

`npm run icons` remakes the app and menu-bar icons from
`../web/public/static/icon.svg`. `npm run dev` runs the app in development.

## Use it

On first launch, enter the dashboard URL, for example
`https://your-linux.your-tailnet.ts.net:8445/`. It must be HTTPS, or HTTP on
localhost for a test hub. It is saved in
`~/Library/Application Support/com.karansag.agent-swarm/settings.json`.

- Closing the window hides it. The Dock icon or the menu-bar **Open dashboard**
  shows it again. ⌘Q quits.
- **Change hub URL…** opens the setup page. Cancel, or saving the same URL,
  goes back to the page you were on. A new URL restarts the app on that hub's
  main page.
- After quitting, the app reopens on the page you left. If that agent is gone,
  the dashboard shows the overview.
- The Dock badge counts agents that need you. Each agent that starts needing
  you gets one notification. Clicking it opens that agent's page.
- **Enable notifications…** asks for permission, or opens notification
  settings if it was refused. **Test notification** sends a test.
- The page keeps polling while the window is hidden (macOS 14 and newer).
  Notifications come from that polling, so the app must be running and the hub
  reachable.

## Security

The hub page can call one app command, `attention`, and only from the exact
origin you saved (scheme, host and port):

```js
window.__TAURI__.core.invoke('attention', { agents: ['otter', 'stoat'] });
```

The page sends the full list on its first poll and then when it changes.

The setup commands work only on the bundled setup page. Links to other origins
open in your browser, not in the app. Changing the URL restarts the app, which
drops the old origin's access. Notifications go through a small Objective-C
bridge to `UNUserNotificationCenter` (`native/notifications.m`), not through
the page.

## Check it

On Linux or a Mac, without WebKit:

```sh
npm test
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo check --manifest-path src-tauri/Cargo.toml --no-default-features
```

On a Mac, with the app from `/Applications` and a scratch hub:

1. First launch: enter the URL and save; the dashboard opens. Quit and reopen;
   it goes straight there.
2. Close the window, reopen it from the menu bar and the Dock. Copy and paste
   work in the chat box. ⌘Q quits.
3. Make an agent need attention: badge 1 and one notification. A reload sends
   no second one. A second agent gives badge 2; clearing both removes it.
   Clicking the notification opens that agent.
4. Hide the window for five minutes, then make an agent need attention; the
   notification still arrives.
5. Open an agent, go to Change hub URL…, and Cancel: the same agent page
   returns. Same after saving the same URL, and after ⌘Q and reopening. An
   invalid URL shows an error and keeps the saved one.
6. Build with `npm run build -- --debug` to get the Web Inspector. From the hub
   page, `setup_info` and `save_hub` must be refused, and `attention` allowed.

## Troubleshooting

To see the notification log, quit the app, then run its binary with stderr
saved:

```sh
"/Applications/Buzz.app/Contents/MacOS/agent-swarm-mac" 2> /tmp/agent-swarm.log
```

If the log stays empty, another copy was already running: the new one hands
over to it and exits. Quit all copies first.

`authorization granted=no error=Error Domain=UNErrorDomain Code=1 "(null)"`
means macOS refused notifications. Check, in order:

- `codesign -dv --verbose=4 "/Applications/Buzz.app"` shows
  `Identifier=com.karansag.agent-swarm` and a `Sealed Resources` line. If not,
  the bundle is not signed; rebuild.
- Only one copy is registered with macOS. Old copies (for example on an
  unmounted DMG) can take the permission. List them with
  `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -dump | grep -B5 com.karansag.agent-swarm`
  and remove one with `lsregister -u "<path>"`.
- Buzz is allowed in System Settings → Notifications.

A `queued` line means macOS accepted the notification. Focus modes and
notification settings can still hide the banner.
