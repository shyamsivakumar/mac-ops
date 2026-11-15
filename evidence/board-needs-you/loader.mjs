// Lets the board code run under plain Node by standing in for the herdr runtime module.
export async function resolve(specifier, context, next) {
  if (specifier === "herdr") return { url: new URL("./herdr-stub.mjs", import.meta.url).href, shortCircuit: true };
  return next(specifier, context);
}
