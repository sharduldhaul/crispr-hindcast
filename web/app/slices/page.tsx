import { redirect } from "next/navigation";

import { PRIMARY_SLICE } from "@/lib/repo";

export default function SlicesIndex() {
  redirect(`/slices/${PRIMARY_SLICE}`);
}
