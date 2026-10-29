const HEX6 = /^#[0-9a-fA-F]{6}$/;
const HEX3 = /^#?([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$/;
const HEX6_LOOSE = /^#?([0-9a-fA-F]{6})$/;

export function isHexColor(value: string): boolean {
  return HEX6.test(value);
}

/** Accepts "36b37e", "#36b37e" or "#3b7"; returns "#36B37E"-style, or null if it isn't a hex color. */
export function normalizeHex(value: string): string | null {
  const text = value.trim();
  const short = HEX3.exec(text);
  if (short) return `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`.toUpperCase();
  const full = HEX6_LOOSE.exec(text);
  return full ? `#${full[1]}`.toUpperCase() : null;
}

function luminance(hex: string): number {
  const channel = (offset: number) => {
    const c = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}

export function contrastRatio(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

const DARK = "#111111";
const LIGHT = "#FFFFFF";

/** Readable text color (dark or white) for a given background, by WCAG contrast. */
export function textColorFor(background: string): string {
  const bg = normalizeHex(background);
  if (!bg) return DARK;
  return contrastRatio(bg, DARK) >= contrastRatio(bg, LIGHT) ? DARK : LIGHT;
}
