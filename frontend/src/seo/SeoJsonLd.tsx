import { useEffect } from 'react'
import { FAQ_ITEMS } from './faqData'
import { SITE_URL } from './siteConfig'

/** 注入 FAQPage JSON-LD（与页面 FAQ 文案同源，避免与 index.html 静态图重复冲突） */
export function SeoJsonLd() {
  useEffect(() => {
    const id = 'seo-faq-jsonld'
    const existing = document.getElementById(id)
    if (existing) existing.remove()

    const payload = {
      '@context': 'https://schema.org',
      '@type': 'FAQPage',
      mainEntity: FAQ_ITEMS.map((item) => ({
        '@type': 'Question',
        name: item.question,
        acceptedAnswer: {
          '@type': 'Answer',
          text: item.answer,
        },
      })),
      url: `${SITE_URL}/`,
    }

    const script = document.createElement('script')
    script.id = id
    script.type = 'application/ld+json'
    script.text = JSON.stringify(payload)
    document.head.appendChild(script)

    return () => {
      document.getElementById(id)?.remove()
    }
  }, [])

  return null
}
