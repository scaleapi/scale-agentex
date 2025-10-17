"use server";

import { notFound, redirect } from "next/navigation";

export default async function Home() {
  // TODO: put an actual page here and link the dev page from home

  if (process.env.NODE_ENV === "development") {
    return redirect("/dev");
  }
  return notFound();
}
