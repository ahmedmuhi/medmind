"""
Database models and operations for MedMind blood test analyzer.
Handles storing and retrieving historical test results for comparison.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./medmind_history.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class TestResult(Base):
    """Model for storing individual blood test results."""
    
    __tablename__ = "test_results"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)  # Simple user identification (can be enhanced later)
    test_name = Column(String, index=True)
    value = Column(Float)
    unit = Column(String)
    reference_low = Column(Float)
    reference_high = Column(Float)
    status = Column(String)  # Normal, High, Low
    created_at = Column(DateTime, default=datetime.utcnow)
    filename = Column(String)  # Original PDF filename
    
class TestSession(Base):
    """Model for storing test session metadata."""
    
    __tablename__ = "test_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    filename = Column(String)
    total_tests = Column(Integer)
    normal_count = Column(Integer)
    abnormal_count = Column(Integer)
    summary_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    """Get database session."""
    db = SessionLocal()
    try:
        return db
    finally:
        pass

def close_db(db: Session):
    """Close database session."""
    db.close()

def store_test_results(
    user_id: str,
    filename: str,
    results: List[Dict[str, Any]],
    summary_message: str,
    db: Session = None
) -> int:
    """
    Store test results in the database.
    
    Args:
        user_id: User identifier
        filename: Original PDF filename
        results: List of test results
        summary_message: Summary of the analysis
        db: Database session
    
    Returns:
        Session ID for the stored results
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        # Create test session
        normal_count = sum(1 for r in results if r["status_short"] == "Normal")
        abnormal_count = len(results) - normal_count
        
        session = TestSession(
            user_id=user_id,
            filename=filename,
            total_tests=len(results),
            normal_count=normal_count,
            abnormal_count=abnormal_count,
            summary_message=summary_message
        )
        db.add(session)
        db.flush()  # Get the session ID
        
        session_id = session.id
        
        # Store individual test results
        for result in results:
            test_result = TestResult(
                user_id=user_id,
                test_name=result["test"],
                value=result["value"],
                unit=result["unit"],
                reference_low=float(result["range"].split(" - ")[0]),
                reference_high=float(result["range"].split(" - ")[1].split(" ")[0]),
                status=result["status_short"],
                filename=filename
            )
            db.add(test_result)
        
        db.commit()
        logger.info(f"Stored {len(results)} test results for user {user_id}")
        return session_id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error storing test results: {e}")
        raise
    finally:
        if should_close:
            close_db(db)

def get_user_history(user_id: str, limit: int = 10, db: Session = None) -> List[Dict[str, Any]]:
    """
    Get user's test history.
    
    Args:
        user_id: User identifier
        limit: Maximum number of sessions to return
        db: Database session
    
    Returns:
        List of test sessions with metadata
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        sessions = db.query(TestSession).filter(
            TestSession.user_id == user_id
        ).order_by(TestSession.created_at.desc()).limit(limit).all()
        
        history = []
        for session in sessions:
            history.append({
                "id": session.id,
                "filename": session.filename,
                "total_tests": session.total_tests,
                "normal_count": session.normal_count,
                "abnormal_count": session.abnormal_count,
                "summary_message": session.summary_message,
                "date": session.created_at.isoformat(),
                "formatted_date": session.created_at.strftime("%B %d, %Y at %I:%M %p")
            })
        
        return history
        
    finally:
        if should_close:
            close_db(db)

def get_test_trends(user_id: str, test_name: str, months: int = 12, db: Session = None) -> Dict[str, Any]:
    """
    Get trends for a specific test over time.
    
    Args:
        user_id: User identifier
        test_name: Name of the test to analyze
        months: Number of months to look back
        db: Database session
    
    Returns:
        Dictionary with trend analysis
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=months * 30)
        
        results = db.query(TestResult).filter(
            TestResult.user_id == user_id,
            TestResult.test_name == test_name,
            TestResult.created_at >= cutoff_date
        ).order_by(TestResult.created_at.asc()).all()
        
        if not results:
            return {"test_name": test_name, "trend": "no_data", "message": "No historical data available"}
        
        # Calculate trend
        values = [r.value for r in results]
        dates = [r.created_at.isoformat() for r in results]
        
        if len(values) < 2:
            return {
                "test_name": test_name,
                "trend": "insufficient_data",
                "message": "Need at least 2 data points for trend analysis",
                "latest_value": values[0],
                "latest_date": dates[0],
                "unit": results[0].unit
            }
        
        # Simple trend calculation
        latest_value = values[-1]
        previous_value = values[-2]
        change = latest_value - previous_value
        percent_change = (change / previous_value) * 100 if previous_value != 0 else 0
        
        # Determine trend direction
        if abs(percent_change) < 5:  # Less than 5% change considered stable
            trend = "stable"
            trend_icon = "➡️"
            trend_message = f"Stable (±{abs(percent_change):.1f}%)"
        elif change > 0:
            trend = "increasing"
            trend_icon = "📈"
            trend_message = f"Increasing (+{percent_change:.1f}%)"
        else:
            trend = "decreasing"
            trend_icon = "📉"
            trend_message = f"Decreasing ({percent_change:.1f}%)"
        
        # Determine if trend is good or concerning
        reference_low = results[-1].reference_low
        reference_high = results[-1].reference_high
        
        # Context for different test types
        improvement_context = ""
        if test_name in ["Total Cholesterol", "LDL", "Triglycerides", "Glucose", "HbA1c"]:
            # Lower is generally better for these tests
            if trend == "decreasing":
                improvement_context = " ✅ Good trend"
            elif trend == "increasing":
                improvement_context = " ⚠️ Monitor closely"
        elif test_name in ["HDL"]:
            # Higher is better for HDL
            if trend == "increasing":
                improvement_context = " ✅ Good trend"
            elif trend == "decreasing":
                improvement_context = " ⚠️ Monitor closely"
        
        return {
            "test_name": test_name,
            "trend": trend,
            "trend_icon": trend_icon,
            "trend_message": trend_message + improvement_context,
            "latest_value": latest_value,
            "previous_value": previous_value,
            "change": change,
            "percent_change": percent_change,
            "values": values,
            "dates": dates,
            "unit": results[0].unit,
            "reference_range": f"{reference_low} - {reference_high}",
            "total_measurements": len(values),
            "timespan_months": months
        }
        
    finally:
        if should_close:
            close_db(db)

def compare_latest_tests(user_id: str, db: Session = None) -> Dict[str, Any]:
    """
    Compare the latest test results with the previous session.
    
    Args:
        user_id: User identifier
        db: Database session
    
    Returns:
        Comparison analysis
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        # Get the two most recent sessions
        recent_sessions = db.query(TestSession).filter(
            TestSession.user_id == user_id
        ).order_by(TestSession.created_at.desc()).limit(2).all()
        
        if len(recent_sessions) < 2:
            return {
                "has_comparison": False,
                "message": "Need at least 2 test sessions for comparison"
            }
        
        latest_session = recent_sessions[0]
        previous_session = recent_sessions[1]
        
        # Get test results for both sessions
        latest_results = db.query(TestResult).filter(
            TestResult.user_id == user_id,
            TestResult.created_at >= latest_session.created_at
        ).all()
        
        previous_results = db.query(TestResult).filter(
            TestResult.user_id == user_id,
            TestResult.created_at >= previous_session.created_at,
            TestResult.created_at < latest_session.created_at
        ).all()
        
        # Create lookup dictionaries
        latest_dict = {r.test_name: r for r in latest_results}
        previous_dict = {r.test_name: r for r in previous_results}
        
        # Find common tests
        common_tests = set(latest_dict.keys()) & set(previous_dict.keys())
        
        comparisons = []
        improvements = 0
        deteriorations = 0
        stable = 0
        
        for test_name in common_tests:
            latest = latest_dict[test_name]
            previous = previous_dict[test_name]
            
            change = latest.value - previous.value
            percent_change = (change / previous.value) * 100 if previous.value != 0 else 0
            
            # Determine if change is significant (>5%)
            if abs(percent_change) < 5:
                change_type = "stable"
                change_icon = "➡️"
                stable += 1
            elif change > 0:
                change_type = "increased"
                change_icon = "📈"
            else:
                change_type = "decreased"
                change_icon = "📉"
            
            # Determine if change is good or bad
            is_improvement = False
            if test_name in ["Total Cholesterol", "LDL", "Triglycerides", "Glucose", "HbA1c"]:
                # Lower is better
                is_improvement = change < 0
            elif test_name in ["HDL"]:
                # Higher is better
                is_improvement = change > 0
            
            if change_type != "stable":
                if is_improvement:
                    improvements += 1
                else:
                    deteriorations += 1
            
            comparisons.append({
                "test_name": test_name,
                "latest_value": latest.value,
                "previous_value": previous.value,
                "change": change,
                "percent_change": percent_change,
                "change_type": change_type,
                "change_icon": change_icon,
                "is_improvement": is_improvement,
                "unit": latest.unit,
                "latest_status": latest.status,
                "previous_status": previous.status
            })
        
        # Sort by absolute percent change (most significant changes first)
        comparisons.sort(key=lambda x: abs(x["percent_change"]), reverse=True)
        
        # Generate summary
        days_between = (latest_session.created_at - previous_session.created_at).days
        
        if improvements > deteriorations:
            overall_trend = "improving"
            trend_icon = "✅"
            summary = f"Great progress! {improvements} tests improved, {deteriorations} need attention."
        elif deteriorations > improvements:
            overall_trend = "concerning"
            trend_icon = "⚠️"
            summary = f"Monitor closely. {deteriorations} tests worsened, {improvements} improved."
        else:
            overall_trend = "mixed"
            trend_icon = "📊"
            summary = f"Mixed results. {improvements} improved, {deteriorations} worsened, {stable} stable."
        
        return {
            "has_comparison": True,
            "latest_date": latest_session.created_at.strftime("%B %d, %Y"),
            "previous_date": previous_session.created_at.strftime("%B %d, %Y"),
            "days_between": days_between,
            "overall_trend": overall_trend,
            "trend_icon": trend_icon,
            "summary": summary,
            "improvements": improvements,
            "deteriorations": deteriorations,
            "stable": stable,
            "total_compared": len(comparisons),
            "comparisons": comparisons
        }
        
    finally:
        if should_close:
            close_db(db)

def get_user_stats(user_id: str, db: Session = None) -> Dict[str, Any]:
    """
    Get overall statistics for a user.
    
    Args:
        user_id: User identifier
        db: Database session
    
    Returns:
        User statistics
    """
    if db is None:
        db = get_db()
        should_close = True
    else:
        should_close = False
    
    try:
        # Get session count
        session_count = db.query(TestSession).filter(TestSession.user_id == user_id).count()
        
        if session_count == 0:
            return {"has_data": False}
        
        # Get first and latest session dates
        first_session = db.query(TestSession).filter(
            TestSession.user_id == user_id
        ).order_by(TestSession.created_at.asc()).first()
        
        latest_session = db.query(TestSession).filter(
            TestSession.user_id == user_id
        ).order_by(TestSession.created_at.desc()).first()
        
        # Calculate tracking period
        tracking_days = (latest_session.created_at - first_session.created_at).days
        
        # Get total test count
        total_tests = db.query(TestResult).filter(TestResult.user_id == user_id).count()
        
        # Get unique test types
        unique_tests = db.query(TestResult.test_name).filter(
            TestResult.user_id == user_id
        ).distinct().count()
        
        return {
            "has_data": True,
            "session_count": session_count,
            "total_tests": total_tests,
            "unique_test_types": unique_tests,
            "tracking_days": tracking_days,
            "first_test_date": first_session.created_at.strftime("%B %d, %Y"),
            "latest_test_date": latest_session.created_at.strftime("%B %d, %Y")
        }
        
    finally:
        if should_close:
            close_db(db)
