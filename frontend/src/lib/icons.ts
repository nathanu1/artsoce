import {
  Armchair,
  BeerStein,
  Bed,
  BookOpen,
  BookmarkSimple,
  Broom,
  ChatsCircle,
  Clover,
  Coffee,
  Confetti,
  CookingPot,
  Drop,
  DropHalf,
  Fire,
  Flower,
  ForkKnife,
  Gift,
  GraduationCap,
  Guitar,
  HandHeart,
  Heart,
  Hourglass,
  Lamp,
  Laptop,
  Leaf,
  Lightbulb,
  MoonStars,
  MusicNotes,
  Notebook,
  PaintBrush,
  PenNib,
  PencilSimple,
  PersonSimpleWalk,
  Plant,
  Scissors,
  Shapes,
  ShoppingBag,
  Shower,
  Smiley,
  Sparkle,
  Spiral,
  Storefront,
  type Icon,
} from "@phosphor-icons/react";

/** Icons named in configs/game (themes, motifs, gifts). Unknown names fall back to Sparkle. */
const BY_NAME: Record<string, Icon> = {
  Armchair,
  BookOpen,
  BookmarkSimple,
  ChatsCircle,
  Clover,
  Coffee,
  Confetti,
  Drop,
  DropHalf,
  Fire,
  Flower,
  Gift,
  HandHeart,
  Heart,
  Lamp,
  Leaf,
  Lightbulb,
  MusicNotes,
  Notebook,
  PaintBrush,
  PenNib,
  Scissors,
  Shapes,
  Smiley,
  Sparkle,
  Spiral,
};

export function iconByName(name: string | undefined): Icon {
  return (name && BY_NAME[name]) || Sparkle;
}

const ACTIVITY_RULES: [RegExp, Icon][] = [
  [/\b(sleep|sleeping|nap|asleep|go(es)? to bed)\b/i, MoonStars],
  [/\b(chat|chatting|talk|conversation)\b/i, ChatsCircle],
  [/\b(coffee|latte|espresso|tea)\b/i, Coffee],
  [/\b(cook|cooking|bake|baking|kitchen)\b/i, CookingPot],
  [/\b(breakfast|lunch|dinner|eat|eating|meal|snack)\b/i, ForkKnife],
  [/\b(party|parties|celebrat\w*|decorat\w*|valentine'?s?)\b/i, Confetti],
  [/\b(write|writing|essay|notes?)\b/i, PencilSimple],
  [/\b(read|reading|book|books|library)\b/i, BookOpen],
  [/\b(study|studying|class|lecture|homework|research|exam)\b/i, GraduationCap],
  [/\b(paint|painting|draw|drawing|sketch\w*|art)\b/i, PaintBrush],
  [/\b(music|guitar|piano|sing|singing|song|compose|composing)\b/i, Guitar],
  [/\b(pub|bar|drink|beer)\b/i, BeerStein],
  [/\b(walk|walking|stroll|jog|jogging|run|running|exercise|workout)\b/i, PersonSimpleWalk],
  [/\b(garden|gardening|plant|plants|water(ing)?|flowers?)\b/i, Plant],
  [/\b(shop|shopping|buy|groceries|errand)\b/i, ShoppingBag],
  [/\b(open|opens|work|working|shift|serve|serving|customers|store|cafe)\b/i, Storefront],
  [/\b(shower|bath|brush|wash|morning routine|get(ting)? ready)\b/i, Shower],
  [/\b(computer|stream|streaming|code|coding|program|email)\b/i, Laptop],
  [/\b(clean|cleaning|tidy|tidying)\b/i, Broom],
  [/\b(wait|waiting)\b/i, Hourglass],
  [/\b(bed|rest|relax|relaxing)\b/i, Bed],
];

export function activityIcon(activity: string): Icon {
  for (const [re, icon] of ACTIVITY_RULES) if (re.test(activity)) return icon;
  return Smiley;
}

/** "have lunch at Hobbs Cafe (getting started)" -> "Having lunch at Hobbs Cafe" style label. */
export function activityLabel(activity: string): string {
  const a = activity.replace(/\s*\((getting started|continued|part \d+)\)\s*$/i, "").trim();
  if (!a) return "Idle";
  return a.charAt(0).toUpperCase() + a.slice(1);
}
