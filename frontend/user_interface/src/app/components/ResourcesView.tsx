import { useState } from 'react';

export function ResourcesView() {
  const [activeResourceTab, setActiveResourceTab] = useState<'indexCollections' | 'llms' | 'embeddings' | 'rerankings' | 'users'>('indexCollections');
  const [viewTab, setViewTab] = useState<'view' | 'add'>('view');
  const [llmName, setLlmName] = useState('');
  const [llmVendor, setLlmVendor] = useState('');
  const [specification, setSpecification] = useState('');
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [embeddingName, setEmbeddingName] = useState('');
  const [embeddingVendor, setEmbeddingVendor] = useState('');
  const [embeddingSpecification, setEmbeddingSpecification] = useState('');
  const [setEmbeddingAsDefault, setSetEmbeddingAsDefault] = useState(false);
  const [rerankingName, setRerankingName] = useState('');
  const [rerankingVendor, setRerankingVendor] = useState('');
  const [rerankingSpecification, setRerankingSpecification] = useState('');
  const [setRerankingAsDefault, setSetRerankingAsDefault] = useState(false);
  const [userTab, setUserTab] = useState<'userlist' | 'createuser'>('userlist');

  return (
    <div className="flex-1 flex flex-col bg-white overflow-hidden">
      {/* Resource Type Tabs */}
      <div className="border-b border-[#e5e5e5]">
        <div className="flex items-center gap-8 px-8 pt-6 pb-3">
          <button
            onClick={() => setActiveResourceTab('indexCollections')}
            className={`pb-2 text-[13px] transition-all border-b-2 ${
              activeResourceTab === 'indexCollections'
                ? 'text-[#1d1d1f] border-[#1d1d1f]'
                : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
            }`}
          >
            Index Collections
          </button>
          <button
            onClick={() => setActiveResourceTab('llms')}
            className={`pb-2 text-[13px] transition-all border-b-2 ${
              activeResourceTab === 'llms'
                ? 'text-[#1d1d1f] border-[#1d1d1f]'
                : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
            }`}
          >
            LLMs
          </button>
          <button
            onClick={() => setActiveResourceTab('embeddings')}
            className={`pb-2 text-[13px] transition-all border-b-2 ${
              activeResourceTab === 'embeddings'
                ? 'text-[#1d1d1f] border-[#1d1d1f]'
                : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
            }`}
          >
            Embeddings
          </button>
          <button
            onClick={() => setActiveResourceTab('rerankings')}
            className={`pb-2 text-[13px] transition-all border-b-2 ${
              activeResourceTab === 'rerankings'
                ? 'text-[#1d1d1f] border-[#1d1d1f]'
                : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
            }`}
          >
            Rerankings
          </button>
          <button
            onClick={() => setActiveResourceTab('users')}
            className={`pb-2 text-[13px] transition-all border-b-2 ${
              activeResourceTab === 'users'
                ? 'text-[#1d1d1f] border-[#1d1d1f]'
                : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
            }`}
          >
            Users
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-8">
          {/* View/Add Tabs - Only show for non-Users tabs */}
          {activeResourceTab !== 'users' && (
            <div className="flex items-center gap-6 mb-8 border-b border-[#e5e5e5]">
              <button
                onClick={() => setViewTab('view')}
                className={`pb-2 text-[13px] transition-all border-b-2 ${
                  viewTab === 'view'
                    ? 'text-[#1d1d1f] border-[#1d1d1f]'
                    : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
                }`}
              >
                View
              </button>
              <button
                onClick={() => setViewTab('add')}
                className={`pb-2 text-[13px] transition-all border-b-2 ${
                  viewTab === 'add'
                    ? 'text-[#1d1d1f] border-[#1d1d1f]'
                    : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
                }`}
              >
                Add
              </button>
            </div>
          )}

          {/* User Tabs - Only show for Users tab */}
          {activeResourceTab === 'users' && (
            <div className="flex items-center gap-6 mb-8 border-b border-[#e5e5e5]">
              <button
                onClick={() => setUserTab('userlist')}
                className={`pb-2 text-[13px] transition-all border-b-2 ${
                  userTab === 'userlist'
                    ? 'text-[#1d1d1f] border-[#1d1d1f]'
                    : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
                }`}
              >
                User list
              </button>
              <button
                onClick={() => setUserTab('createuser')}
                className={`pb-2 text-[13px] transition-all border-b-2 ${
                  userTab === 'createuser'
                    ? 'text-[#1d1d1f] border-[#1d1d1f]'
                    : 'text-[#86868b] border-transparent hover:text-[#1d1d1f]'
                }`}
              >
                Create user
              </button>
            </div>
          )}

          {viewTab === 'view' ? (
            <>
              {activeResourceTab === 'indexCollections' && (
                <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
                      <tr>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          id
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          name
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          index_type
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">1</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">File Collection</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">FileIndex</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">2</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">GraphRAG Collection</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">GraphRAGIndex</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">3</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LightRAG Collection</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LightRAGIndex</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {activeResourceTab === 'llms' && (
                <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
                      <tr>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          name
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          vendor
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          default
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">openai</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">ChatOpenAI</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">claude</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCAnthropicChat</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">google</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCGeminiChat</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">true</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">groq</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">ChatOpenAI</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">cohere</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCCohereChat</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">mistral</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">ChatOpenAI</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {activeResourceTab === 'embeddings' && (
                <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
                      <tr>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          name
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          vendor
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          default
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">openai</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">OpenAIEmbeddings</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">cohere</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCCohereEmbeddings</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">google</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCGoogleEmbeddings</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">true</td>
                      </tr>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">mistral</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">LCMistralEmbeddings</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">false</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {activeResourceTab === 'rerankings' && (
                <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
                  <table className="w-full">
                    <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
                      <tr>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          name
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          vendor
                        </th>
                        <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                          default
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-[#e5e5e5] last:border-b-0">
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">cohere</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">CohereReranking</td>
                        <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">true</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}

              {activeResourceTab === 'users' && (
                <div>
                  {userTab === 'userlist' && (
                    <div className="border border-[#e5e5e5] rounded-lg overflow-hidden">
                      <table className="w-full">
                        <thead className="bg-[#fafafa] border-b border-[#e5e5e5]">
                          <tr>
                            <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                              username
                            </th>
                            <th className="text-left px-4 py-3 text-[12px] text-[#1d1d1f] font-normal">
                              admin
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="border-b border-[#e5e5e5] last:border-b-0">
                            <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">admin</td>
                            <td className="px-4 py-4 text-[13px] text-[#1d1d1f]">true</td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}

                  {userTab === 'createuser' && (
                    <div className="py-12 text-center text-[13px] text-[#86868b]">
                      Create user form
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              {activeResourceTab === 'llms' && (
                <div className="flex gap-6">
                  {/* Left Panel - Form */}
                  <div className="w-[400px]">
                    {/* LLM name */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        LLM name
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Must be unique. The name will be used to identify the LLM.
                      </p>
                      <input
                        type="text"
                        value={llmName}
                        onChange={(e) => setLlmName(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      />
                    </div>

                    {/* LLM vendors */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        LLM vendors
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Choose the vendor for the LLM. Each vendor has different specification.
                      </p>
                      <select
                        value={llmVendor}
                        onChange={(e) => setLlmVendor(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      >
                        <option value="">Select vendor</option>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="google">Google</option>
                        <option value="groq">Groq</option>
                        <option value="cohere">Cohere</option>
                        <option value="mistral">Mistral</option>
                      </select>
                    </div>

                    {/* Specification */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Specification
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Specification of the LLM in YAML format
                      </p>
                      <textarea
                        value={specification}
                        onChange={(e) => setSpecification(e.target.value)}
                        className="w-full px-3 py-3 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[12px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b] resize-none min-h-[120px] font-mono"
                      />
                    </div>

                    {/* Set as default */}
                    <div className="mb-6">
                      <p className="text-[11px] text-[#86868b] mb-2">
                        Set this LLM as default. This default LLM will be used by default across the application.
                      </p>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={setAsDefault}
                          onChange={(e) => setSetAsDefault(e.target.checked)}
                          className="w-4 h-4 rounded border-[#d2d2d7] text-[#1d1d1f] focus:ring-0 focus:ring-offset-0"
                        />
                        <span className="text-[13px] text-[#1d1d1f]">Set default</span>
                      </label>
                    </div>

                    {/* Add LLM Button */}
                    <button className="w-full px-4 py-3 bg-[#1d1d1f] hover:bg-[#424245] text-white rounded-lg text-[13px] font-medium transition-all">
                      Add LLM
                    </button>
                  </div>

                  {/* Right Panel - Spec Description */}
                  <div className="flex-1 bg-[#fafafa] rounded-lg p-6">
                    <h3 className="text-[15px] text-[#1d1d1f] font-medium mb-4">
                      Spec description
                    </h3>
                    <p className="text-[13px] text-[#86868b]">
                      Select an LLM to view the spec description.
                    </p>
                  </div>
                </div>
              )}

              {activeResourceTab === 'embeddings' && (
                <div className="flex gap-6">
                  {/* Left Panel - Form */}
                  <div className="w-[400px]">
                    {/* Embedding name */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Embedding name
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Must be unique. The name will be used to identify the embedding.
                      </p>
                      <input
                        type="text"
                        value={embeddingName}
                        onChange={(e) => setEmbeddingName(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      />
                    </div>

                    {/* Embedding vendors */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Embedding vendors
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Choose the vendor for the embedding. Each vendor has different specification.
                      </p>
                      <select
                        value={embeddingVendor}
                        onChange={(e) => setEmbeddingVendor(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      >
                        <option value="">Select vendor</option>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="google">Google</option>
                        <option value="groq">Groq</option>
                        <option value="cohere">Cohere</option>
                        <option value="mistral">Mistral</option>
                      </select>
                    </div>

                    {/* Specification */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Specification
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Specification of the embedding in YAML format
                      </p>
                      <textarea
                        value={embeddingSpecification}
                        onChange={(e) => setEmbeddingSpecification(e.target.value)}
                        className="w-full px-3 py-3 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[12px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b] resize-none min-h-[120px] font-mono"
                      />
                    </div>

                    {/* Set as default */}
                    <div className="mb-6">
                      <p className="text-[11px] text-[#86868b] mb-2">
                        Set this embedding as default. This default embedding will be used by default across the application.
                      </p>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={setEmbeddingAsDefault}
                          onChange={(e) => setSetEmbeddingAsDefault(e.target.checked)}
                          className="w-4 h-4 rounded border-[#d2d2d7] text-[#1d1d1f] focus:ring-0 focus:ring-offset-0"
                        />
                        <span className="text-[13px] text-[#1d1d1f]">Set default</span>
                      </label>
                    </div>

                    {/* Add Embedding Button */}
                    <button className="w-full px-4 py-3 bg-[#1d1d1f] hover:bg-[#424245] text-white rounded-lg text-[13px] font-medium transition-all">
                      Add Embedding
                    </button>
                  </div>

                  {/* Right Panel - Spec Description */}
                  <div className="flex-1 bg-[#fafafa] rounded-lg p-6">
                    <h3 className="text-[15px] text-[#1d1d1f] font-medium mb-4">
                      Spec description
                    </h3>
                    <p className="text-[13px] text-[#86868b]">
                      Select an embedding to view the spec description.
                    </p>
                  </div>
                </div>
              )}

              {activeResourceTab === 'rerankings' && (
                <div className="flex gap-6">
                  {/* Left Panel - Form */}
                  <div className="w-[400px]">
                    {/* Reranking name */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Reranking name
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Must be unique. The name will be used to identify the reranking.
                      </p>
                      <input
                        type="text"
                        value={rerankingName}
                        onChange={(e) => setRerankingName(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      />
                    </div>

                    {/* Reranking vendors */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Reranking vendors
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Choose the vendor for the reranking. Each vendor has different specification.
                      </p>
                      <select
                        value={rerankingVendor}
                        onChange={(e) => setRerankingVendor(e.target.value)}
                        className="w-full px-3 py-2 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[13px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b]"
                      >
                        <option value="">Select vendor</option>
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                        <option value="google">Google</option>
                        <option value="groq">Groq</option>
                        <option value="cohere">Cohere</option>
                        <option value="mistral">Mistral</option>
                      </select>
                    </div>

                    {/* Specification */}
                    <div className="mb-6">
                      <label className="block text-[13px] text-[#1d1d1f] font-medium mb-2">
                        Specification
                      </label>
                      <p className="text-[11px] text-[#86868b] mb-3">
                        Specification of the reranking in YAML format
                      </p>
                      <textarea
                        value={rerankingSpecification}
                        onChange={(e) => setRerankingSpecification(e.target.value)}
                        className="w-full px-3 py-3 bg-[#fafafa] border border-[#e5e5e5] rounded-lg text-[12px] text-[#1d1d1f] focus:outline-none focus:border-[#86868b] resize-none min-h-[120px] font-mono"
                      />
                    </div>

                    {/* Set as default */}
                    <div className="mb-6">
                      <p className="text-[11px] text-[#86868b] mb-2">
                        Set this reranking as default. This default reranking will be used by default across the application.
                      </p>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={setRerankingAsDefault}
                          onChange={(e) => setSetRerankingAsDefault(e.target.checked)}
                          className="w-4 h-4 rounded border-[#d2d2d7] text-[#1d1d1f] focus:ring-0 focus:ring-offset-0"
                        />
                        <span className="text-[13px] text-[#1d1d1f]">Set default</span>
                      </label>
                    </div>

                    {/* Add Reranking Button */}
                    <button className="w-full px-4 py-3 bg-[#1d1d1f] hover:bg-[#424245] text-white rounded-lg text-[13px] font-medium transition-all">
                      Add Reranking
                    </button>
                  </div>

                  {/* Right Panel - Spec Description */}
                  <div className="flex-1 bg-[#fafafa] rounded-lg p-6">
                    <h3 className="text-[15px] text-[#1d1d1f] font-medium mb-4">
                      Spec description
                    </h3>
                    <p className="text-[13px] text-[#86868b]">
                      Select a reranking to view the spec description.
                    </p>
                  </div>
                </div>
              )}

              {activeResourceTab !== 'llms' && activeResourceTab !== 'embeddings' && activeResourceTab !== 'rerankings' && (
                <div className="py-12 text-center text-[13px] text-[#86868b]">
                  Add new {activeResourceTab} form
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}