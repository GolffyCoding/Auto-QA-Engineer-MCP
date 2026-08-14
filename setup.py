from setuptools import setup, find_packages

setup(
    name="qa-mcp",
    version="0.1.0",
    description="Autonomous QA Engineer MCP Platform",
    author="QA-MCP Team",
    packages=find_packages(),
    install_requires=[
        "mcp>=1.2",
        "pydantic>=2.0",
        "httpx>=0.24",
        "playwright>=1.40",
        "selenium>=4.15",
        "robotframework>=7.0",
        "robotframework-seleniumlibrary>=6.2",
        "pytest>=7.4",
        "pytest-asyncio>=0.21",
        "jinja2>=3.1",
        "pyyaml>=6.0",
        "Appium-Python-Client>=4.0",
        "gitpython>=3.1",
        "requests>=2.31",
        "sqlalchemy>=2.0",
        "aiofiles>=23.0",
        "rich>=13.0",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "qa-mcp=qa_mcp.mcp_server:main",
            "qa-mcp-serve=qa_mcp.server:main",
        ],
    },
)
