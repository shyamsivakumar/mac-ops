/**
 * Task router: registers task/* virtual models, each an ordered fallback chain of physical models.
 * Models without credentials or inside a quota/rate-limit block are skipped. Blocks are shared
 * across pi processes through ~/.pi/agent/task-router-blocks.json. Provider quota errors that pi
 * does not retry are caught on agent_end, the model is blocked, and the turn is resumed on the
 * next model in the chain.
 *
 * Source of truth: mac-ops runtime/pi/extensions/task-router.ts, installed to
 * ~/.pi/agent/extensions/task-router.ts by install_agents.py.
 *
 * Routing policy (Shyam 2026-11-17, mac-ops #497): builds start on GLM 5.3 or
 * MiniMax; no OpenAI-API model (Sol, Terra, Luna, GPT) appears in any chain.
 * Reviews are not routed here at all: they run only on GPT-6.2 Astra through
 * the coordinator gate chain, so this file deliberately registers no review
 * route.
 */

import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, ExtensionContext, ModelRoute, ModelRouteRequest } from "@earendil-works/pi-coding-agent";

const PROVIDER = "task";

const ROUTES: Record<string, string[]> = {
	quick: ["minimax/MiniMax-M3.1-Flash:low", "deepseek/deepseek-flash:low", "pi-claude-cli/claude-haiku-5-5:low"],
	chore: ["minimax/MiniMax-M3.1-Flash:medium", "deepseek/deepseek-flash:medium"],
	standard: [
		"minimax/MiniMax-M3.1-Flash:medium",
		"zai/glm-5.3:medium",
		"deepseek/deepseek-flash:medium",
		"cursor/composer-2.5:medium",
	],
	ui: ["minimax/MiniMax-M3.1-Flash:medium", "zai/glm-5.3:medium", "deepseek/deepseek-flash:medium", "pi-claude-cli/claude-sonnet-5-5:medium"],
	research: ["minimax/MiniMax-M3.1-Flash:medium", "zai/glm-5.3:medium", "deepseek/deepseek-flash:medium"],
	rca: ["zai/glm-5.3:high", "minimax/MiniMax-M3.1-Flash:high", "pi-claude-cli/claude-opus-5-5:high"],
	risky: ["zai/glm-5.3:high", "minimax/MiniMax-M3.1-Flash:high", "pi-claude-cli/claude-opus-5-5:high"],
	design: ["zai/glm-5.3:high", "minimax/MiniMax-M3.1-Flash:high", "pi-claude-cli/claude-opus-5-5:high"],
	hard: ["zai/glm-5.3:xhigh", "minimax/MiniMax-M3.1-Flash:xhigh", "pi-claude-cli/claude-fable-5-2:xhigh", "pi-claude-cli/claude-opus-5-5:xhigh"],
};

const BLOCKS_PATH = join(homedir(), ".pi", "agent", "task-router-blocks.json");
const QUOTA_BLOCK_MS = 60 * 60_000;
const RATE_LIMIT_BLOCK_MS = 2 * 60_000;
const MAX_AUTO_RESUMES = 2;
const RESUME_PROMPT = "Your last request failed on a provider quota limit. Continue the task from where you stopped.";

const HARD_QUOTA =
	/monthly usage limit reached|insufficient_quota|quota exceeded|billing|out of budget|available balance|insufficient.?balance|"code":"?402|^402:|"code":"1308"/i;
const OVERLOADED = /overloaded/i;
const LIMIT = /429|rate.?limit|limit|exhausted|usage|quota/i;
const QUOTA_LIKE = /quota|exhausted|usage|billing|budget|balance|1308|1310|limit reached|weekly|monthly/i;
const RESET_TIME = /(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)(Z|[+-]\d{2}:?\d{2})?/;

type Level = ModelRoute["thinkingLevel"];
type RouterState = { retried?: string };
type Request = ModelRouteRequest<RouterState>;
type Block = { until: number; reason: string };

interface Entry {
	provider: string;
	id: string;
	key: string;
	level: Level;
}

const chains: Record<string, Entry[]> = Object.fromEntries(
	Object.entries(ROUTES).map(([route, specs]) => [route, specs.map(parseEntry)]),
);

function parseEntry(spec: string): Entry {
	const colon = spec.lastIndexOf(":");
	const key = spec.slice(0, colon);
	const slash = key.indexOf("/");
	return { provider: key.slice(0, slash), id: key.slice(slash + 1), key, level: spec.slice(colon + 1) as Level };
}

function readBlocks(): Record<string, Block> {
	if (!existsSync(BLOCKS_PATH)) return {};
	try {
		return JSON.parse(readFileSync(BLOCKS_PATH, "utf8"));
	} catch {
		return {};
	}
}

function activeBlocks(): Record<string, Block> {
	const now = Date.now();
	return Object.fromEntries(Object.entries(readBlocks()).filter(([, block]) => block.until > now));
}

function writeBlocks(blocks: Record<string, Block>): void {
	const temp = `${BLOCKS_PATH}.${process.pid}.tmp`;
	try {
		writeFileSync(temp, JSON.stringify(blocks, null, 2));
		renameSync(temp, BLOCKS_PATH);
	} catch (error) {
		console.error(`task-router: could not write ${BLOCKS_PATH}: ${error}`);
	}
}

function blockDuration(errorMessage: string): number {
	const match = RESET_TIME.exec(errorMessage);
	if (match) {
		const reset = new Date(`${match[1]}T${match[2]}${match[3] ?? ""}`).getTime();
		if (reset > Date.now()) return reset - Date.now();
	}
	return QUOTA_LIKE.test(errorMessage) ? QUOTA_BLOCK_MS : RATE_LIMIT_BLOCK_MS;
}

function blockModel(key: string, errorMessage: string): void {
	writeBlocks({
		...activeBlocks(),
		[key]: { until: Date.now() + blockDuration(errorMessage), reason: errorMessage.slice(0, 200) },
	});
}

function usability(entry: Entry, ctx: ExtensionContext, blocks: Record<string, Block>): string | undefined {
	const model = ctx.modelRegistry.find(entry.provider, entry.id);
	if (!model) return "not in the model catalog";
	if (!ctx.modelRegistry.hasConfiguredAuth(model)) return "no credentials";
	const block = blocks[entry.key];
	if (block) return `blocked until ${new Date(block.until).toISOString()} (${block.reason})`;
	return undefined;
}

function pickEntry(
	route: string,
	ctx: ExtensionContext,
	after: number,
): { entry: Entry; index: number } | undefined {
	const blocks = activeBlocks();
	const chain = chains[route];
	for (let index = after + 1; index < chain.length; index++) {
		if (!usability(chain[index], ctx, blocks)) return { entry: chain[index], index };
	}
	return undefined;
}

function exhausted(route: string, ctx: ExtensionContext, failedKey?: string, failedNote?: string): Error {
	const blocks = activeBlocks();
	const tried = chains[route].map((entry) => {
		if (entry.key === failedKey) return `${entry.key}: ${failedNote}`;
		return `${entry.key}: ${usability(entry, ctx, blocks) ?? "skipped after the failed model"}`;
	});
	return new Error(`task/${route} has no usable model left. Tried:\n${tried.join("\n")}`);
}

function route(request: Request, ctx: ExtensionContext): ModelRoute<RouterState> {
	const name = request.model.id;
	const chain = chains[name];

	if (request.reason === "continuation" && request.previous) {
		return { model: request.previous.model, thinkingLevel: request.previous.thinkingLevel ?? "medium" };
	}

	let after = -1;
	let state: RouterState | undefined = request.state?.retried ? {} : undefined;
	let failedKey: string | undefined;
	let failedNote: string | undefined;

	if (request.reason === "retry" && request.failed) {
		const { model, message } = request.failed;
		failedKey = `${model.provider}/${model.id}`;
		const errorMessage = message.errorMessage ?? "";
		failedNote = `failed: ${errorMessage.slice(0, 200)}`;
		after = chain.findIndex((entry) => entry.key === failedKey);
		const limitHit = LIMIT.test(errorMessage) && !OVERLOADED.test(errorMessage);
		if (limitHit) {
			blockModel(failedKey, errorMessage);
		} else if (request.state?.retried !== failedKey && after >= 0) {
			return { model, thinkingLevel: request.failed.thinkingLevel ?? chain[after].level, state: { retried: failedKey } };
		}
	}

	const picked = pickEntry(name, ctx, after);
	if (!picked) throw exhausted(name, ctx, failedKey, failedNote);
	const model = ctx.modelRegistry.find(picked.entry.provider, picked.entry.id)!;
	return { model, thinkingLevel: picked.entry.level, state };
}

function smallestWindow(name: string, ctx: ExtensionContext): number | undefined {
	const windows = chains[name].flatMap((entry) => {
		const model = ctx.modelRegistry.find(entry.provider, entry.id);
		return model ? [model.contextWindow] : [];
	});
	return windows.length ? Math.min(...windows) : undefined;
}

export default function (pi: ExtensionAPI) {
	const definition = (name: string, contextWindow?: number) => ({
		provider: PROVIDER,
		id: name,
		name: `Task: ${name}`,
		thinkingLevels: ["medium"] as Level[],
		contextWindow,
		route,
	});

	for (const name of Object.keys(ROUTES)) pi.registerVirtualModel<RouterState>(definition(name));

	pi.on("session_start", async (_event, ctx) => {
		for (const name of Object.keys(ROUTES)) {
			const contextWindow = smallestWindow(name, ctx);
			if (contextWindow) pi.registerVirtualModel<RouterState>(definition(name, contextWindow));
		}
	});

	let resumes = 0;
	let resumePending = false;

	pi.on("input", async (event) => {
		if (event.source !== "extension") resumes = 0;
	});

	pi.on("agent_end", async (event, ctx) => {
		if (ctx.model?.provider !== PROVIDER || !chains[ctx.model.id]) return;
		const last = event.messages.findLast((message) => message.role === "assistant");
		if (last?.role !== "assistant" || last.stopReason !== "error") return;
		const errorMessage = last.errorMessage ?? "";
		if (!HARD_QUOTA.test(errorMessage) || resumes >= MAX_AUTO_RESUMES) return;

		const key = `${last.provider}/${last.model}`;
		const name = ctx.model.id;
		blockModel(key, errorMessage);
		const next = pickEntry(name, ctx, -1);
		if (!next) {
			ctx.ui.notify(`task/${name}: ${key} hit a quota limit and no other model is usable.`, "error");
			return;
		}
		ctx.ui.notify(`task/${name}: blocked ${key} (quota). Next: ${next.entry.key}.`, "warning");
		resumes++;
		resumePending = true;
	});

	pi.on("agent_settled", async () => {
		if (!resumePending) return;
		resumePending = false;
		pi.sendUserMessage(RESUME_PROMPT);
	});
}
