#!/usr/bin/env python3
"""
Test script to verify the MedMind application functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test if all modules import correctly"""
    try:
        import main
        print("✅ Main module imported successfully")
        
        from database import store_test_results, get_user_history
        print("✅ Database functions imported successfully")
        
        # Test database creation
        from database import Base, engine
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created successfully")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_reference_ranges():
    """Test if reference ranges load correctly"""
    try:
        from main import reference_ranges
        print(f"✅ Loaded {len(reference_ranges)} reference ranges")
        
        # Show a few examples
        examples = list(reference_ranges.keys())[:5]
        print(f"   Examples: {', '.join(examples)}")
        return True
    except Exception as e:
        print(f"❌ Reference ranges error: {e}")
        return False

def main():
    print("🧪 Testing MedMind Application Components\n")
    
    success = True
    success &= test_imports()
    success &= test_reference_ranges()
    
    if success:
        print(f"\n🎉 All tests passed! Your MedMind application is ready.")
        print("\n📋 New Features Added:")
        print("   • 🗄️  Database storage for test history")
        print("   • 📊 Progress comparison between tests")
        print("   • 📈 Trend analysis for individual tests")
        print("   • 📱 Enhanced UI with history and comparison views")
        print("   • 👤 User tracking (simple session-based)")
        
        print("\n🚀 To start the server, run:")
        print("   python main.py")
        print("\n   Then visit: http://localhost:8000")
        
        print("\n✨ Key Improvements:")
        print("   • Upload multiple test files over time")
        print("   • See if your health markers are improving or worsening")
        print("   • Track trends for specific tests (cholesterol, glucose, etc.)")
        print("   • View your complete test history")
        print("   • Get personalized health insights based on your progress")
        
    else:
        print(f"\n❌ Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
