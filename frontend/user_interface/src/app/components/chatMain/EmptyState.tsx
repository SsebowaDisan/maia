function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center">
      <div className="max-w-2xl w-full text-center space-y-3">
        <div className="w-16 h-16 bg-gradient-to-br from-[#1d1d1f] to-[#3a3a3c] rounded-2xl mx-auto mb-4 flex items-center justify-center shadow-lg">
          <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        </div>
        <h1 className="text-[28px] tracking-tight text-[#1d1d1f]">
          This is the beginning of a new conversation.
        </h1>
        <p className="text-[15px] text-[#86868b] leading-relaxed">
          Start by uploading files or URLs from the sidebar.
        </p>
      </div>
    </div>
  );
}

export { EmptyState };
