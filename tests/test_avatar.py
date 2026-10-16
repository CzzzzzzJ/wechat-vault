import unittest
from backend.avatar import AvatarReader
class AvatarTests(unittest.TestCase):
 def test_only_known_https_hosts(self):
  self.assertEqual(AvatarReader.safe_url('http://wx.qlogo.cn/a?q=1'),'https://wx.qlogo.cn/a?q=1')
  for u in ('file:///etc/passwd','https://localhost/a','https://wx.qlogo.cn.evil.com/a','https://user@wx.qlogo.cn/a','https://wx.qlogo.cn:9000/a','data:image/png,x'):
   self.assertIsNone(AvatarReader.safe_url(u))
