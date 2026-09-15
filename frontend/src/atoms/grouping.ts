import { atom } from "jotai";
import type { GroupingMode } from "../hierarchy/definitions";

export const groupingModeAtom = atom<GroupingMode>("none");
