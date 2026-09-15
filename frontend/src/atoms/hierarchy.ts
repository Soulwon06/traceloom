import { atom } from "jotai";

export const collapsedHierarchyNodeIdsAtom = atom<Set<string>>(new Set<string>());
