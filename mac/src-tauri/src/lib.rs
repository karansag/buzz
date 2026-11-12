//! Portable URL, persistence, and attention logic; native shell lives in app.rs.
use percent_encoding::{utf8_percent_encode, AsciiSet, NON_ALPHANUMERIC};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, fs, io::Write, path::Path};
use url::{Host, Url};

const AGENT_FRAGMENT: &AsciiSet = &NON_ALPHANUMERIC
    .remove(b'-')
    .remove(b'_')
    .remove(b'.')
    .remove(b'~');

#[cfg(all(feature = "desktop", target_os = "macos"))]
pub mod app;
#[cfg(all(feature = "desktop", target_os = "macos"))]
mod notifications;

/// Bounded deduplication across dashboard reloads in one app process.
#[derive(Default)]
pub struct AgentNotifications {
    seen: BTreeSet<i64>,
    floor: i64,
}

impl AgentNotifications {
    pub fn accept(&mut self, id: i64, agent: &str, body: &str) -> Result<bool, String> {
        if id <= 0
            || agent.is_empty()
            || agent.chars().count() > 128
            || agent.chars().any(char::is_control)
            || body.trim().is_empty()
            || body.chars().count() > 1000
            || body.contains('\0')
        {
            return Err("Invalid agent notification".into());
        }
        if id <= self.floor || !self.seen.insert(id) {
            return Ok(false);
        }
        if self.seen.len() > 512 {
            self.floor = self.seen.pop_first().unwrap();
        }
        Ok(true)
    }
}

#[derive(Clone, Debug)]
pub struct HubUrl(Url);

impl HubUrl {
    pub fn parse(input: &str) -> Result<Self, String> {
        let url = Url::parse(input.trim()).map_err(|_| "Enter a full https:// dashboard URL.")?;
        let loopback = match url.host() {
            Some(Host::Domain("localhost")) => true,
            Some(Host::Ipv4(ip)) => ip.is_loopback(),
            Some(Host::Ipv6(ip)) => ip.is_loopback(),
            _ => false,
        };
        if url.host().is_none()
            || (url.scheme() != "https" && !(url.scheme() == "http" && loopback))
        {
            return Err("Use HTTPS, or HTTP on localhost for a local test hub.".into());
        }
        if !url.username().is_empty() || url.password().is_some() || url.query().is_some() {
            return Err("Use the dashboard URL without credentials or query parameters.".into());
        }
        Ok(Self(url))
    }

    pub fn url(&self) -> &Url {
        &self.0
    }
    pub fn origin_pattern(&self) -> String {
        format!("{}/*", self.0.origin().ascii_serialization())
    }
    pub fn allows(&self, url: &Url) -> bool {
        self.0.origin() == url.origin()
    }
    pub fn restore(&self, last_url: Option<&str>) -> Url {
        last_url
            .and_then(|value| Url::parse(value).ok())
            .filter(|url| self.allows(url) && url.username().is_empty() && url.password().is_none())
            .unwrap_or_else(|| self.0.clone())
    }
    pub fn agent_url(&self, name: &str) -> Url {
        let mut url = self.0.clone();
        let encoded = utf8_percent_encode(name, AGENT_FRAGMENT);
        url.set_fragment(Some(&format!("/agent/{encoded}")));
        url
    }
}

#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub hub_url: Option<String>,
    #[serde(default)]
    pub last_url: Option<String>,
}

impl Settings {
    pub fn load(path: &Path) -> Result<Self, String> {
        match fs::read(path) {
            Ok(bytes) => serde_json::from_slice(&bytes)
                .map_err(|e| format!("Could not read saved hub settings: {e}")),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(Self::default()),
            Err(e) => Err(format!("Could not read saved hub settings: {e}")),
        }
    }

    pub fn save(path: &Path, hub: &HubUrl, last_url: Option<&Url>) -> Result<(), String> {
        let parent = path.parent().ok_or("Missing settings directory")?;
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        let mut file = tempfile::NamedTempFile::new_in(parent).map_err(|e| e.to_string())?;
        let settings = Self {
            hub_url: Some(hub.url().to_string()),
            last_url: last_url
                .filter(|url| hub.allows(url))
                .map(|url| url.to_string()),
        };
        file.write_all(&serde_json::to_vec_pretty(&settings).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        file.as_file().sync_all().map_err(|e| e.to_string())?;
        file.persist(path).map_err(|e| e.to_string())?;
        Ok(())
    }
}

#[derive(Clone, Default)]
pub struct Attention {
    names: BTreeSet<String>,
}

impl Attention {
    pub fn update(&mut self, agents: Vec<String>) -> Result<(usize, Vec<String>), String> {
        if agents.len() > 512
            || agents
                .iter()
                .any(|s| s.is_empty() || s.len() > 128 || s.chars().any(char::is_control))
        {
            return Err("Invalid attention list".into());
        }
        let current: BTreeSet<_> = agents.into_iter().collect();
        let added = current.difference(&self.names).cloned().collect();
        let count = current.len();
        self.names = current;
        Ok((count, added))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hub_origin_includes_scheme_and_port() {
        let hub = HubUrl::parse(" https://linux.example.ts.net:8445/#/ ").unwrap();
        assert_eq!(hub.origin_pattern(), "https://linux.example.ts.net:8445/*");
        assert!(hub
            .allows(&Url::parse("https://linux.example.ts.net:8445/other#/agent/otter").unwrap()));
        for other in [
            "https://linux.example.ts.net/",
            "https://evil.example/",
            "http://linux.example.ts.net:8445/",
        ] {
            assert!(!hub.allows(&Url::parse(other).unwrap()));
        }
    }

    #[test]
    fn rejects_unsafe_hubs_and_accepts_loopback_test_hubs() {
        for bad in [
            "file:///tmp/a",
            "javascript:alert(1)",
            "http://tailnet.example/",
            "https://user:secret@example.com/",
            "https://example.com/?token=secret",
            "example.com",
        ] {
            assert!(HubUrl::parse(bad).is_err(), "{bad}");
        }
        for good in [
            "http://127.0.0.1:8798/",
            "http://[::1]:8798/",
            "http://localhost:8798/",
            "https://example.com/dashboard/#/",
        ] {
            assert!(HubUrl::parse(good).is_ok(), "{good}");
        }
    }

    #[test]
    fn explicit_notifications_validate_and_deduplicate() {
        let mut tracker = AgentNotifications::default();
        assert!(tracker.accept(2, "fake-agent", "Done").unwrap());
        assert!(tracker.accept(1, "fake-agent", "Earlier").unwrap());
        assert!(!tracker.accept(2, "fake-agent", "Done").unwrap());
        for (id, agent, body) in [
            (0, "fake", "done"),
            (3, "bad\nagent", "done"),
            (3, "fake", ""),
            (3, "fake", "bad\0body"),
        ] {
            assert!(tracker.accept(id, agent, body).is_err());
        }
        assert!(tracker.accept(3, "fake", "Done").unwrap());
        assert!(tracker.accept(4, "fake", &"a".repeat(1001)).is_err());
        for id in 5..600 {
            assert!(tracker.accept(id, "fake", "Done").unwrap());
        }
        assert_eq!(tracker.seen.len(), 512);
        assert!(!tracker.accept(1, "fake", "Done").unwrap());
    }

    #[test]
    fn attention_deduplicates_and_only_notifies_on_entry() {
        let mut attention = Attention::default();
        assert_eq!(
            attention
                .update(vec!["otter".into(), "otter".into()])
                .unwrap(),
            (1, vec!["otter".into()])
        );
        assert_eq!(attention.update(vec!["otter".into()]).unwrap(), (1, vec![]));
        assert_eq!(
            attention
                .update(vec!["stoat".into(), "otter".into()])
                .unwrap(),
            (2, vec!["stoat".into()])
        );
        assert_eq!(attention.update(vec![]).unwrap(), (0, vec![]));
        assert_eq!(
            attention.update(vec!["otter".into()]).unwrap(),
            (1, vec!["otter".into()])
        );
    }

    #[test]
    fn invalid_attention_does_not_replace_the_previous_list() {
        let mut attention = Attention::default();
        attention.update(vec!["otter".into()]).unwrap();
        assert!(attention.update(vec!["\n".into()]).is_err());
        assert_eq!(attention.update(vec!["otter".into()]).unwrap(), (1, vec![]));
    }

    #[test]
    fn settings_are_atomic_and_survive_replacement() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        assert!(Settings::load(&path).unwrap().hub_url.is_none());
        let first = HubUrl::parse("https://one.example:8445/").unwrap();
        Settings::save(&path, &first, None).unwrap();
        assert_eq!(
            Settings::load(&path).unwrap().hub_url.unwrap(),
            first.url().as_str()
        );
        let second = HubUrl::parse("https://two.example:8445/").unwrap();
        Settings::save(&path, &second, None).unwrap();
        assert_eq!(
            Settings::load(&path).unwrap().hub_url.unwrap(),
            second.url().as_str()
        );
        fs::write(&path, b"bad json").unwrap();
        assert!(Settings::load(&path).is_err());
    }

    #[test]
    fn restores_the_full_route_only_for_the_selected_origin() {
        let hub = HubUrl::parse("https://linux.example:8445/dashboard/#/").unwrap();
        let route = "https://linux.example:8445/dashboard/#/agent/otter";
        assert_eq!(hub.restore(Some(route)).as_str(), route);
        for invalid in [
            "https://other.example/#/agent/otter",
            "https://linux.example:8446/#/",
            "broken",
            "https://user:secret@linux.example:8445/#/",
        ] {
            assert_eq!(hub.restore(Some(invalid)), *hub.url());
        }
        assert_eq!(hub.agent_url("otter").as_str(), route);
        assert_eq!(hub.agent_url("a/b").fragment(), Some("/agent/a%2Fb"));
        assert_eq!(
            hub.agent_url("an agent").fragment(),
            Some("/agent/an%20agent")
        );
    }

    #[test]
    fn last_route_survives_restart_but_not_a_change_of_hub() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("settings.json");
        let hub = HubUrl::parse("https://one.example:8445/").unwrap();
        let route = hub.agent_url("otter");
        Settings::save(&path, &hub, Some(&route)).unwrap();
        let saved = Settings::load(&path).unwrap();
        assert_eq!(hub.restore(saved.last_url.as_deref()), route);
        let other = HubUrl::parse("https://two.example:8445/").unwrap();
        Settings::save(&path, &other, None).unwrap();
        assert!(Settings::load(&path).unwrap().last_url.is_none());
        fs::write(&path, br#"{"hub_url":"https://one.example:8445/"}"#).unwrap();
        assert!(Settings::load(&path).unwrap().last_url.is_none());
    }
}
