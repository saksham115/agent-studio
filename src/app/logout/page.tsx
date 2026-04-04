import { signOut } from "@/lib/auth"
import { redirect } from "next/navigation"

export default async function LogoutPage() {
  await signOut({ redirect: false })
  redirect("/login")
}
