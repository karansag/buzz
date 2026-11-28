//! Name pool for server-assigned handles, and validation of requested ones.

use std::collections::HashSet;

fn pool() -> Vec<&'static str> {
    include_str!("pool.txt").lines().filter(|l| !l.is_empty()).collect()
}

/// A pool name that none of `taken` uses. A handle from an earlier version
/// such as "otter-opus" reserves bare "otter". When every name is taken, a
/// number is appended.
pub fn pick(taken: &HashSet<String>) -> String {
    let pool = pool();
    let free = |name: &str| {
        !taken.contains(name) && !taken.iter().any(|t| t.strip_prefix(name).is_some_and(|r| r.starts_with('-')))
    };
    let candidates: Vec<&str> = pool.iter().copied().filter(|n| free(n)).collect();
    if !candidates.is_empty() {
        return candidates[fastrand::usize(..candidates.len())].to_string();
    }
    let base = pool[fastrand::usize(..pool.len())];
    (2..).map(|n| format!("{base}-{n}")).find(|name| !taken.contains(name)).unwrap_or_default()
}

/// Validate an agent-requested handle and return its canonical form.
pub fn normalize_requested(name: &str) -> Result<String, String> {
    let candidate = name.trim().to_lowercase();
    let mut chars = candidate.chars();
    let ok = |c: char| c.is_ascii_lowercase() || c.is_ascii_digit();
    let valid = candidate.len() <= 48 && chars.next().is_some_and(ok) && chars.all(|c| ok(c) || c == '-');
    if !valid {
        return Err(
            "name must be 1-48 characters of lowercase letters, digits or hyphens, and start with a letter or digit"
                .into(),
        );
    }
    if candidate == "owner" || candidate == "hub" {
        return Err(format!("'{candidate}' is a reserved handle"));
    }
    Ok(candidate)
}
