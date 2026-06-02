import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold mt-6 mb-3 text-gray-900">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-semibold mt-5 mb-2 text-gray-900">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-semibold mt-4 mb-2 text-gray-800">{children}</h3>
  ),
  p: ({ children }) => (
    <p className="mb-4 text-gray-700 leading-relaxed">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="list-disc pl-6 mb-4 text-gray-700 space-y-1">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-6 mb-4 text-gray-700 space-y-1">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  a: ({ href, children }) => (
    <a
      href={href}
      className="text-blue-600 underline hover:text-blue-800"
      {...(href ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-gray-300 pl-4 my-4 text-gray-500 italic">
      {children}
    </blockquote>
  ),
  pre: ({ children }) => (
    <pre className="bg-gray-50 border border-gray-200 rounded p-4 overflow-x-auto my-4">
      {children}
    </pre>
  ),
  code: ({ children, className }) => {
    const isBlock = className?.startsWith('language-') || String(children ?? '').includes('\n');
    if (isBlock) {
      return (
        <code className={`text-sm font-mono text-gray-800 ${className ?? ''}`}>{children}</code>
      );
    }
    return (
      <code className="bg-gray-100 rounded px-1 py-0.5 text-sm font-mono text-gray-800">
        {children}
      </code>
    );
  },
  hr: () => <hr className="my-6 border-gray-200" />,
};

interface Props {
  content: string;
}

export default function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
