// The three herdr calls the board's loader makes, backed by the real machine.
import { execFile } from "node:child_process";
import { readFileSync } from "node:fs";

export const home = () => process.env.HOME;

export const readTextFile = async (path) => {
  if (path.endsWith("decisions.json") && process.env.PROOF_DECISIONS) return readFileSync(process.env.PROOF_DECISIONS, "utf8");
  try {
    return readFileSync(path, "utf8");
  } catch {
    return null;
  }
};

export const exec = (command, args) =>
  new Promise((resolve) => {
    execFile(command, args, { maxBuffer: 64 * 1024 * 1024 }, (error, stdout, stderr) => {
      resolve({ code: error ? (typeof error.code === "number" ? error.code : 1) : 0, stdout: stdout ?? "", stderr: stderr ?? "" });
    });
  });
