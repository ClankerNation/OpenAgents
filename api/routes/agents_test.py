import pytest
from unittest.mock import patch, MagicMock
from .agents import validate_endpoint_url, is_private_ip

def test_validate_endpoint_url_valid():
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        url = "https://google.com"
        assert validate_endpoint_url(url) == url

def test_validate_endpoint_url_invalid_scheme():
    url = "ftp://google.com"
    with pytest.raises(ValueError, match="URL scheme must be http or https"):
        validate_endpoint_url(url)

def test_validate_endpoint_url_private_ip():
    url = "http://192.168.1.1"
    with pytest.raises(ValueError, match="URL points to a private/internal IP address"):
        validate_endpoint_url(url)

def test_is_private_ip_resolves():
    with patch('socket.getaddrinfo') as mock_getaddrinfo:
        # Mock resolving to local IP
        mock_getaddrinfo.return_value = [(None, None, None, None, ('127.0.0.1', 80))]
        assert is_private_ip("attacker.com") is True

def test_validate_endpoint_url_unreachable():
    with patch('urllib.request.urlopen') as mock_urlopen:
        mock_urlopen.side_effect = Exception("Unreachable")
        url = "https://some-unreachable-site.com"
        with pytest.raises(ValueError, match="Error checking endpoint reachability"):
            validate_endpoint_url(url)
