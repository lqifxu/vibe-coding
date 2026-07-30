import { useEffect } from 'react'
import { FAQ_ITEMS } from './faqData'
import { HOWTO_GUIDES } from './geoCopy'
import { SITE_URL } from './siteConfig'

function injectJsonLd(id: string, payload: unknown) {
  document.getElementById(id)?.remove()
  const script = document.createElement('script')
  script.id = id
  script.type = 'application/ld+json'
  script.text = JSON.stringify(payload)
  document.head.appendChild(script)
}

/** 注入 FAQPage + HowTo JSON-LD（与页面文案同源） */
export function SeoJsonLd() {
  useEffect(() => {
    injectJsonLd('seo-faq-jsonld', {
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
    })

    injectJsonLd('seo-howto-jsonld', {
      '@context': 'https://schema.org',
      '@graph': HOWTO_GUIDES.map((guide) => ({
        '@type': 'HowTo',
        '@id': `${SITE_URL}/#${guide.id}`,
        name: guide.name,
        description: guide.description,
        inLanguage: 'zh-CN',
        step: guide.steps.map((step, index) => ({
          '@type': 'HowToStep',
          position: index + 1,
          name: step.name,
          text: step.text,
        })),
      })),
    })

    return () => {
      document.getElementById('seo-faq-jsonld')?.remove()
      document.getElementById('seo-howto-jsonld')?.remove()
    }
  }, [])

  return null
}
