#!/bin/bash
# Quick Integration Test Script
# Uruchamia podstawowe testy integracji

echo "=================================================="
echo "  RTK Rover - Integration Test Runner"
echo "=================================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found!"
    exit 1
fi

echo "✅ Python3 found: $(python3 --version)"
echo ""

# Check if in venv
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "⚠️  Warning: Not in virtual environment"
    echo "   Activate with: source venv/bin/activate"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Run integration tests
echo "=================================================="
echo "Running Integration Tests..."
echo "=================================================="
echo ""

python3 test_integration.py
TEST_RESULT=$?

echo ""
echo "=================================================="

if [ $TEST_RESULT -eq 0 ]; then
    echo "✅ ALL TESTS PASSED!"
    echo ""
    echo "Next steps:"
    echo "1. Review INTEGRATION_CHECKLIST.md"
    echo "2. Run: python run.py"
    echo "3. Test API: curl http://localhost:5000/api/rover/test"
else
    echo "❌ SOME TESTS FAILED"
    echo ""
    echo "Check logs above for details."
    echo "See FAQ.md for troubleshooting."
fi

echo "=================================================="

exit $TEST_RESULT
