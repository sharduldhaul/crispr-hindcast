import Link from "next/link";

export default function NotFound() {
  return (
    <div className="wrap page">
      <div className="eyebrow">404</div>
      <h1>Not in the record.</h1>
      <p className="lede" style={{ marginTop: 18 }}>
        Nothing here matches. The system would refuse to guess, and so will this page.
      </p>
      <p style={{ marginTop: 24 }}>
        <Link href="/">Back to the overview</Link> · <Link href="/genes">Search genes</Link>
      </p>
    </div>
  );
}
