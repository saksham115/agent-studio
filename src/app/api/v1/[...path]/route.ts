import { NextRequest, NextResponse } from "next/server"
import { auth } from "@/lib/auth"
import { SignJWT } from "jose"

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const AUTH_SECRET = process.env.AUTH_SECRET || ""

async function createBackendToken(user: { id?: string; email?: string | null; name?: string | null }) {
  const secret = new TextEncoder().encode(AUTH_SECRET)
  return new SignJWT({
    sub: user.id || "",
    email: user.email || "",
    name: user.name || "",
    org_id: "00000000-0000-0000-0000-000000000000", // Default org for now
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("1h")
    .sign(secret)
}

async function proxyRequest(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const session = await auth()
  if (!session?.user) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 })
  }

  const { path } = await context.params
  const backendPath = `/api/v1/${path.join("/")}`
  const url = new URL(backendPath, BACKEND_URL)

  // Forward query params
  req.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value)
  })

  const token = await createBackendToken(session.user)

  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  }

  // Forward content-type (but not for GET/HEAD)
  const contentType = req.headers.get("content-type")
  if (contentType) {
    headers["Content-Type"] = contentType
  }

  const fetchOptions: RequestInit = {
    method: req.method,
    headers,
  }

  // Forward body for non-GET requests
  if (req.method !== "GET" && req.method !== "HEAD") {
    if (contentType?.includes("multipart/form-data")) {
      // For file uploads, forward the raw body and let fetch set the boundary
      const formData = await req.formData()
      fetchOptions.body = formData
      delete headers["Content-Type"] // Let fetch set it with boundary
    } else {
      fetchOptions.body = await req.text()
    }
  }

  try {
    const res = await fetch(url.toString(), fetchOptions)

    const responseHeaders = new Headers()
    res.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "transfer-encoding") {
        responseHeaders.set(key, value)
      }
    })

    if (res.status === 204) {
      return new NextResponse(null, { status: 204, headers: responseHeaders })
    }

    const body = await res.arrayBuffer()
    return new NextResponse(body, {
      status: res.status,
      headers: responseHeaders,
    })
  } catch (error) {
    console.error("Backend proxy error:", error)
    return NextResponse.json(
      { detail: "Backend service unavailable" },
      { status: 502 }
    )
  }
}

export const GET = proxyRequest
export const POST = proxyRequest
export const PUT = proxyRequest
export const DELETE = proxyRequest
export const PATCH = proxyRequest
