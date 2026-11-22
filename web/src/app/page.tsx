export default function Home() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">getpaid</h1>
      <p className="mt-2 text-gray-600">
        Drafts follow-ups for overdue invoices. Nothing is sent without your
        approval.
      </p>
      <a
        href="/drafts"
        className="mt-6 inline-block rounded bg-black px-4 py-2 text-white"
      >
        Review reminders
      </a>
    </main>
  );
}
