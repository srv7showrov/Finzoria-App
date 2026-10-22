import type { en } from "./en";

export type MessageKey = keyof typeof en;
/** Every locale must provide every key; the compiler rejects missing or extra keys. */
export type Messages = { readonly [K in MessageKey]: string };
