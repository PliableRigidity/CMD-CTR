export const DEFAULT_REGION_LABELS = ["United Kingdom", "Global"];

export function formatRegionLabel(region) {
  if (region === "United Kingdom") {
    return "UK";
  }
  return region;
}
