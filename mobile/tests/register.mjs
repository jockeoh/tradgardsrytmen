// Native host primitives and router focus are mocked; screens, hooks, session and transport are real.
import { registerHooks } from "node:module";
const mocks = new Map([
  ["react-native", "./support/native.mjs"],
  ["react-native-safe-area-context", "./support/native.mjs"],
  ["expo-router", "./support/router.mjs"],
  ["expo-crypto", "./support/crypto.mjs"],
]);
registerHooks({
  resolve(specifier, context, next) {
    if (mocks.has(specifier))
      return {
        url: new URL(mocks.get(specifier), import.meta.url).href,
        shortCircuit: true,
      };
    return next(specifier, context);
  },
});
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
