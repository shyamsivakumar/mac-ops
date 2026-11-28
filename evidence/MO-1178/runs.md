## Proof run: red 1dab2c1791f22a41318cf4da3ad78c71945126d6

```sh
python3 -c 'from pathlib import Path; md = Path("coordinator/pi/subagent-manager/agents/researcher.md"); yml = Path("coordinator/pi/subagent-manager/agents/researcher.yml"); assert md.exists() and not yml.exists(), "researcher.md missing or researcher.yml still present"; text = md.read_text(); assert "/Users/shyamsivakumar/Code/llmwiki/runtime/codex/skills/research/SKILL.md" in text and "morph/morph-dsv41flash" in text, "researcher.md missing skill pointer or model pin"'
```

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
AssertionError: researcher.md missing or researcher.yml still present

```

{"state": "red", "exit": 1, "matched": true, "ref": "1dab2c1791f22a41318cf4da3ad78c71945126d6"}
## Proof run: green d082c15a837fe47f8ad10d1eb460aa1489780b97

```sh
python3 -c 'from pathlib import Path; md = Path("coordinator/pi/subagent-manager/agents/researcher.md"); yml = Path("coordinator/pi/subagent-manager/agents/researcher.yml"); assert md.exists() and not yml.exists(), "researcher.md missing or researcher.yml still present"; text = md.read_text(); assert "/Users/shyamsivakumar/Code/llmwiki/runtime/codex/skills/research/SKILL.md" in text and "morph/morph-dsv41flash" in text, "researcher.md missing skill pointer or model pin"'
```

```

```

{"state": "green", "exit": 0, "matched": null, "ref": "d082c15a837fe47f8ad10d1eb460aa1489780b97"}
