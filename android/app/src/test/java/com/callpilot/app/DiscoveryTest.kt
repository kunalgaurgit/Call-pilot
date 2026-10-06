package com.callpilot.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DiscoveryTest {

    @Test
    fun testValidReply() {
        assertEquals("http://192.168.1.100:8001", parseDiscoveryReply("CALLPILOT 8001", "192.168.1.100"))
        assertEquals("http://10.0.0.5:8002", parseDiscoveryReply("CALLPILOT 8002", "10.0.0.5"))
        assertEquals("http://192.168.137.1:65535", parseDiscoveryReply("CALLPILOT 65535", "192.168.137.1"))
    }

    @Test
    fun testValidReplyWithWhitespace() {
        assertEquals("http://192.168.1.100:8001", parseDiscoveryReply("  CALLPILOT 8001  ", "192.168.1.100"))
        assertEquals("http://192.168.1.100:8001", parseDiscoveryReply("CALLPILOT   8001\n", "192.168.1.100"))
        assertEquals("http://192.168.1.100:8001", parseDiscoveryReply("\tCALLPILOT\t8001\r\n", "192.168.1.100"))
    }

    @Test
    fun testInvalidPrefix() {
        assertNull(parseDiscoveryReply("SERVER 8001", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT_DISCOVER", "192.168.1.100"))
        assertNull(parseDiscoveryReply("callpilot 8001", "192.168.1.100"))
    }

    @Test
    fun testInvalidPort() {
        assertNull(parseDiscoveryReply("CALLPILOT abc", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT 0", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT 70000", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT -8001", "192.168.1.100"))
    }

    @Test
    fun testEmptyOrMalformed() {
        assertNull(parseDiscoveryReply("", "192.168.1.100"))
        assertNull(parseDiscoveryReply("   ", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT", "192.168.1.100"))
        assertNull(parseDiscoveryReply("CALLPILOT 8001 extra", "192.168.1.100"))
    }
}
