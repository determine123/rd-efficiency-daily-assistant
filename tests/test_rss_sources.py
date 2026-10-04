import unittest

from app.connectors_rss import parse_rss


class RSSSourceTests(unittest.TestCase):
    def test_channel_title_preserves_source_without_feed_url(self):
        records = parse_rss(b'<rss><channel><title>Engineering News</title><item><title>Agent</title><link>https://example.com/article</link></item></channel></rss>')
        self.assertEqual(records[0]['source_name'], 'Engineering News')

    def test_atom_self_link_does_not_replace_article(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><title>News</title><entry><title>Agent</title><link rel="self" href="https://example.com/feed/1"/><link rel="enclosure" href="https://example.com/audio.mp3"/><link rel="alternate" href="https://example.com/article"/></entry></feed>'
        self.assertEqual(parse_rss(xml)[0]['url'], 'https://example.com/article')

    def test_atom_self_only_has_no_article_link(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Agent</title><link rel="self" href="https://example.com/feed/1"/></entry></feed>'
        self.assertEqual(parse_rss(xml)[0]['url'], '')

    def test_item_source_overrides_channel(self):
        xml = b'<rss><channel><title>Aggregator</title><item><title>Agent</title><source>Original Publisher</source></item></channel></rss>'
        self.assertEqual(parse_rss(xml)[0]['source_name'], 'Original Publisher')
