## Your `config.yml` is now safe from PackageManager updates.

Previously, when PackageManager reinstalled the driver (after a Venus OS firmware update or manual reinstall), it would extract the release tarball and **overwrite your custom `config.yml`** with the default template — silently losing your tank names, capacities, alarms, and `enabled` settings.

This release fixes that by excluding `config.yml` from the tarball entirely.

---

## 🔒 What changed

| Before | After |
|---|---|
| `config.yml` included in release tarball | `config.yml` excluded via `.gitattributes` |
| PackageManager overwrites your config on every update | PackageManager preserves your config — never touched |
| No template for new users | `config.yml.example` provided as a reference template |

**How it works:**

1. `.gitattributes` marks `config.yml` with `export-ignore` — GitHub's archive API omits it from tarballs
2. `config.yml.example` is the new default template included in every release
3. The `setup` script copies `config.yml.example` → `config.yml` **only if config.yml doesn't already exist**
4. PackageManager updates never touch your config because it's not in the tarball

---

## 📦 Install / Update

```bash
wget -qO - https://github.com/alexsanzder/dbus-ads1115/archive/latest.tar.gz | tar -xzf - -C /data
rm -rf /data/dbus-ads1115
mv /data/dbus-ads1115-latest /data/dbus-ads1115
/data/dbus-ads1115/setup
```

Or via **PackageManager GUI** — Owner: `alexsanzder` · Repository: `dbus-ads1115` · Branch: `latest`

> **Safe to update:** Your existing `/data/dbus-ads1115/config.yml` will be preserved.

---

## 📖 Full setup guide, wiring diagrams and configuration reference in the [README](https://github.com/alexsanzder/dbus-ads1115#readme).
