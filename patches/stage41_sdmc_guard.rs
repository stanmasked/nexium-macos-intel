// Stage41: disposable, synthetic He-Man lab SD only.
// This is a lexical + existing-symlink guard, NOT race-free confinement.
pub(crate) fn stage41_guest_sd_path(
    root: &std::path::Path,
    guest: &str,
) -> Option<std::path::PathBuf> {
    if guest.len() > 512 || guest.contains('\0') || guest.contains('\\') {
        return None;
    }
    let relative = guest.strip_prefix("sdmc:/")?;
    let parts: Vec<&str> = relative.split('/').collect();
    let allowed = matches!(
        parts.as_slice(),
        ["switch"]
            | ["switch", "heman_lore_lab"]
            | ["switch", "heman_lore_lab", "progress0.bin"]
            | ["switch", "heman_lore_lab", "progress1.bin"]
    );
    if !allowed || parts.iter().any(|p| {
        p.is_empty() || *p == "." || *p == ".." ||
            p.contains(':') || p.bytes().any(|b| b < 32 || b == 127)
    }) {
        return None;
    }
    if let Ok(meta) = std::fs::symlink_metadata(root) {
        if meta.file_type().is_symlink() || !meta.is_dir() {
            return None;
        }
    }
    let mut host = root.to_path_buf();
    for (index, part) in parts.iter().enumerate() {
        host.push(part);
        match std::fs::symlink_metadata(&host) {
            Ok(meta) => {
                if meta.file_type().is_symlink()
                    || (index + 1 < parts.len() && !meta.is_dir())
                {
                    return None;
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return None,
        }
    }
    Some(host)
}

#[cfg(test)]
mod stage41_sdmc_guard_tests {
    use super::stage41_guest_sd_path;
    use std::path::Path;
    #[test]
    fn exact_private_lab_slots_only() {
        let root = Path::new("/stage41-isolated-unknown-root");
        for guest in [
            "sdmc:/switch", "sdmc:/switch/heman_lore_lab",
            "sdmc:/switch/heman_lore_lab/progress0.bin",
            "sdmc:/switch/heman_lore_lab/progress1.bin",
        ] {
            assert!(stage41_guest_sd_path(root, guest).is_some(), "{guest}");
        }
        for guest in [
            "", "sdmc:/", "sdmc:/../logs/escape.bin",
            "sdmc:/switch/../../outside", "sdmc:/switch/heman_lore_lab/../logs",
            "sdmc:/switch/heman_lore_lab/./progress0.bin",
            "sdmc:/switch/heman_lore_lab/progress2.bin",
            "sdmc:/switch/heman_lore_lab/progress0.bin/",
            "sdmc:/switch/heman_lore_lab/other/file.bin",
            "/etc/passwd", "C:/Windows/temp.txt",
            "sdmc:////switch/heman_lore_lab/progress0.bin",
            "sdmc:/switch\\..\\outside",
            "sdmc:/switch/heman_lore_lab/progress0.bin\0other",
        ] {
            assert!(stage41_guest_sd_path(root, guest).is_none(), "{guest}");
        }
    }
    #[cfg(unix)]
    #[test]
    fn existing_symlink_does_not_escape() {
        use std::os::unix::fs::symlink;
        let name = format!(
            "stage41-sdmc-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        );
        let folder = std::env::temp_dir().join(name);
        let root = folder.join("sdmc");
        std::fs::create_dir_all(root.join("switch")).unwrap();
        symlink(std::env::temp_dir(), root.join("switch/heman_lore_lab")).unwrap();
        assert!(stage41_guest_sd_path(
            &root, "sdmc:/switch/heman_lore_lab/progress0.bin"
        ).is_none());
        std::fs::remove_dir_all(&folder).unwrap();
    }
    #[cfg(unix)]
    #[test]
    fn root_symlink_is_rejected() {
        use std::os::unix::fs::symlink;
        let folder = std::env::temp_dir().join(format!(
            "stage41-root-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
        ));
        std::fs::create_dir(&folder).unwrap();
        symlink(std::env::temp_dir(), folder.join("sdmc")).unwrap();
        assert!(stage41_guest_sd_path(
            &folder.join("sdmc"), "sdmc:/switch/heman_lore_lab"
        ).is_none());
        std::fs::remove_dir_all(&folder).unwrap();
    }
}
