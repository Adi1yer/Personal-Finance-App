import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

export const QUARTER_ENDS: Record<number, string> = {
  1: "03-31",
  2: "06-30",
  3: "09-30",
  4: "12-31",
};

export const QUARTER_STARTS: Record<number, string> = {
  1: "01-01",
  2: "04-01",
  3: "07-01",
  4: "10-01",
};

export function quarterRange(year: number, quarter: number) {
  return {
    start: `${year}-${QUARTER_STARTS[quarter]}`,
    end: `${year}-${QUARTER_ENDS[quarter]}`,
  };
}
