#!/usr/bin/env python3
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import moltbook_launch_manager as mlm

with open(mlm.CREDENTIALS_FILE) as f:
    creds = json.load(f)
api_key = creds["api_key"]

# 1. Fetch profile to find post IDs
profile = mlm.api_request(f'/agents/profile?name={creds["agent_name"]}', api_key=api_key)
recent_posts = profile.get("recentPosts", [])

post_ids = [p.get("id") for p in recent_posts if p.get("id")]
# Check if new post was recorded
extra_known = []
results_file = Path("/tmp/interaction_and_coverage_results.json")
if results_file.exists():
    try:
        with open(results_file) as rf:
            rdata = json.load(rf)
            mp = rdata.get("master_post", {})
            mpid = mp.get("post", {}).get("id") or mp.get("id") or mp.get("content_id")
            if mpid:
                extra_known.append(mpid)
    except Exception:
        pass

extra_known += [
    "1f9d687f-a92d-4e98-bd90-75668b47a0f5",
    "c36852de-254d-42bb-9ccc-d016688b3900",
    "bc6f448a-0232-40be-ae66-1a438b0925a4",
    "cdc4cab6-f4a7-4e56-b198-a498ed9d1ab0",
    "f44d20d4-c018-474b-ba73-a134e714216d",
    "ee89c6f1-ef54-4960-bb9b-5c697fb0bf04",
    "d1022c9a-b580-4672-9271-110aa07dee43",
    "24b899fe-af1e-4a9b-8328-b9f9ffd597a5",
    "d693109b-7d25-4432-838e-90743a6d13ec",
    "75e7a3dd-b0f9-4cb5-be3c-547e4757f82c",
    "79e877f6-8a3f-46cd-be9f-99de4df95412",
    "e7c0adba-990a-4511-8d04-b29de045b3e3",
    "dd9ada7b-2baa-438d-b146-423af683bf52",
    "82f293bc-132b-42c1-a684-f212df7fc3db",
    "29cb1ff3-65f8-4e0e-9cd3-a501a1aab3f6",
    "a21a0b27-de2c-4cdd-bd38-6e61b1949b01",
    "74b9e6a6-f23c-420d-a987-c7c312679a48",
]
for pid in extra_known:
    if pid not in post_ids:
        post_ids.append(pid)

print(f"Total post IDs to analyze: {len(post_ids)}")

# 2. Fetch all 45 tools from mcp_server
sys.path.insert(0, str(SCRIPTS_DIR.parent / "agents"))
from mcp_server import MoltbookMonetizationMCPServer

server = MoltbookMonetizationMCPServer()
all_tools = [t["name"] for t in server.list_tools()]
print(f"Total production tools: {len(all_tools)}\n")

tool_mentions = {t: [] for t in all_tools}
analyzed_posts = []

for pid in post_ids:
    res = mlm.api_request(f"/posts/{pid}", method="GET", api_key=api_key)
    p = res.get("post", res)
    title = p.get("title", "Untitled")
    submolt = p.get("submolt", {}).get("name") if isinstance(p.get("submolt"), dict) else p.get("submolt")
    content = p.get("content", "")
    comments_count = p.get("comment_count", p.get("comments_count", 0))
    upvotes = p.get("upvotes", 0)

    analyzed_posts.append({
        "id": pid,
        "title": title,
        "submolt": submolt,
        "content_length": len(content),
        "comments": comments_count,
        "upvotes": upvotes,
        "content": content
    })

    # Check which tools are mentioned
    for tool in all_tools:
        # Match function name or clean name without underscores
        tool_clean = tool.replace("_", " ")
        if tool.lower() in content.lower() or tool.lower() in title.lower() or (len(tool_clean) > 8 and tool_clean.lower() in content.lower()):
            tool_mentions[tool].append(pid)

# Summary of posts
print("=== PUBLICACIONES AUTORIZADAS ENCONTRADAS ===")
for idx, ap in enumerate(analyzed_posts, 1):
    print(f"{idx}. [{ap['id'][:8]}] m/{ap['submolt']} | {ap['title']}")
    print(f"   Longitud: {ap['content_length']} chars | Comentarios: {ap['comments']} | Upvotes: {ap['upvotes']}")

print("\n=== MATRIZ DE COBERTURA DE HERRAMIENTAS (45 TOOLS) ===")
covered_tools = [t for t, pids in tool_mentions.items() if len(pids) > 0]
uncovered_tools = [t for t, pids in tool_mentions.items() if len(pids) == 0]

print(f"Herramientas con post explícito: {len(covered_tools)} / {len(all_tools)} ({len(covered_tools)/len(all_tools)*100:.1f}%)")
print(f"Herramientas sin post explícito: {len(uncovered_tools)} / {len(all_tools)} ({len(uncovered_tools)/len(all_tools)*100:.1f}%)\n")

print("--- HERRAMIENTAS CUBIERTAS ---")
for t in covered_tools:
    print(f"  [X] {t} -> Posts: {tool_mentions[t]}")

print("\n--- HERRAMIENTAS PENDIENTES DE POST ---")
for t in uncovered_tools:
    print(f"  [ ] {t}")
