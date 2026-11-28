## Proof run: red 3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151

```sh
d=$(mktemp -d); mkdir "$d/bin"; : > "$d/p.png"
py=$(command -v python3)
err=$(HOME="$d" PATH="$d/bin" "$py" coordinator/pi/bin/kpane "$d/p.png" 2>&1 >/dev/null); code=$?
if [ "$code" -ne 0 ] && [ "$(printf '%s\n' "$err" | wc -l)" -eq 1 ] && printf '%s' "$err" | grep -q "kpane mod is not installed"; then echo "ok: $err"; else echo "NOT CLEAR: exit=$code err=$err"; exit 1; fi
```

```
NOT CLEAR: exit=1 err=kpane: herdr-app could not run: [Errno 2] No such file or directory: 'herdr-app'
kpane: cannot open the picture: [Errno 2] No such file or directory: 'open'

```

{"state": "red", "exit": 1, "matched": true, "ref": "3da3cdbfbdbf536eaf3199bc7f48549b8b0a8151"}
## Proof run: green eab7f88c0b65973abbf14e3f246ab6b9fef4a8a5

```sh
d=$(mktemp -d); mkdir "$d/bin"; : > "$d/p.png"
py=$(command -v python3)
err=$(HOME="$d" PATH="$d/bin" "$py" coordinator/pi/bin/kpane "$d/p.png" 2>&1 >/dev/null); code=$?
if [ "$code" -ne 0 ] && [ "$(printf '%s\n' "$err" | wc -l)" -eq 1 ] && printf '%s' "$err" | grep -q "kpane mod is not installed"; then echo "ok: $err"; else echo "NOT CLEAR: exit=$code err=$err"; exit 1; fi
```

```
ok: kpane: the kpane mod is not installed at /var/folders/d3/kwh8z2bj1rlgy6ld9fcpnpk00000gn/T/tmp.XyMnnoOi7I/.config/herdr-app/mods/kpane

```

{"state": "green", "exit": 0, "matched": null, "ref": "eab7f88c0b65973abbf14e3f246ab6b9fef4a8a5"}
