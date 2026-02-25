import infoPanelImage from "../../assets/0510e4bc98561e87825eccff32a3d70ddd7d9644.png";

export function HelpView() {
  return (
    <div className="flex-1 flex flex-col bg-white overflow-hidden">
      {/* Header with version */}
      <div className="border-b border-[#e5e5e5] px-8 py-6 flex items-center justify-between">
        <h1 className="text-[22px] text-[#1d1d1f] font-medium">Help</h1>
        <span className="text-[13px] text-[#86868b]">version: 0.01</span>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-8 space-y-8">
          {/* 1. Conversation Settings Panel */}
          <div className="space-y-4">
            <h2 className="text-[17px] text-[#1d1d1f] font-medium">
              1. Conversation Settings Panel
            </h2>
            
            <div className="space-y-3 pl-6">
              <div className="space-y-2">
                <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                  Here you can select, create, rename, and delete conversations.
                </p>
                
                <div className="space-y-2 pl-6">
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    By default, a new conversation is created automatically if no conversation is selected.
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                  Below that you have the file index, where you can choose whether to disable, select all files, or select which files to retrieve references from.
                </p>
                
                <div className="space-y-2 pl-6">
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    If you choose "Disabled", no files will be considered as context during chat.
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    If you choose "Search All", all files will be considered during chat.
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    If you choose "Select", a dropdown will appear for you to select the files to be considered during chat. If no files are selected, then no files will be considered during chat.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* 2. Chat Panel */}
          <div className="space-y-4">
            <h2 className="text-[17px] text-[#1d1d1f] font-medium">
              2. Chat Panel
            </h2>
            
            <div className="pl-6">
              <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                This is where you can chat with the chatbot.
              </p>
            </div>
          </div>

          {/* 3. Information Panel */}
          <div className="space-y-4">
            <h2 className="text-[17px] text-[#1d1d1f] font-medium">
              3. Information Panel
            </h2>

            {/* Information panel image */}
            <div className="pl-6">
              <img 
                src={infoPanelImage} 
                alt="information panel" 
                className="w-auto h-auto max-w-full rounded-lg border border-[#e5e5e5]"
              />
            </div>

            <div className="space-y-3 pl-6">
              <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                Supporting information such as the retrieved evidence and reference will be displayed here.
              </p>

              <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                Direct citation for the answer produced by the LLM is highlighted.
              </p>

              <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                The confidence score of the answer and relevant scores of evidences are displayed to quickly assess the quality of the answer and retrieved content.
              </p>

              <div className="space-y-3">
                <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                  Meaning of the score displayed:
                </p>

                <div className="space-y-2 pl-6">
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    <span className="font-medium">Answer confidence</span>: answer confidence level from the LLM model.
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    <span className="font-medium">Relevance score</span>: overall relevant score between evidence and user question.
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    <span className="font-medium">Vectorstore score</span>: relevant score from vector embedding similarity calculation (show{' '}
                    <code className="px-2 py-0.5 bg-[#f5f5f7] rounded text-[12px] font-mono text-[#1d1d1f]">
                      full-text search
                    </code>{' '}
                    if retrieved from full-text search DB).
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    <span className="font-medium">LLM relevant score</span>: relevant score from LLM model (which judge relevancy between question and evidence using specific prompt).
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] leading-relaxed">
                    <span className="font-medium">Reranking score</span>: relevant score from Cohere{' '}
                    <a 
                      href="https://docs.cohere.com/reference/rerank" 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-[#1d1d1f] underline hover:text-[#424245] transition-colors"
                    >
                      reranking model
                    </a>.
                  </p>
                </div>
              </div>

              <div className="bg-[#f5f5f7] rounded-lg p-4 mt-4">
                <p className="text-[13px] text-[#1d1d1f] leading-relaxed font-mono">
                  Generally, the score quality is{' '}
                  <code className="px-2 py-0.5 bg-white rounded text-[12px]">
                    LLM relevant score &gt; Reranking score &gt; Vectorscore
                  </code>
                  . By default, overall relevance score is taken directly from
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
