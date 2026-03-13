#!/usr/bin/env python3
"""
EA Mode CLI Tool

Quick command-line interface for managing executives, annotations, and relationships.
Useful for testing and administrative tasks.

Usage:
    python ea_cli.py executives list
    python ea_cli.py executives create --name "John Doe" --email "john@example.com"
    python ea_cli.py annotations create --executive-id 1 --event-id "abc123" --priority high
    python ea_cli.py relationships create --executive-id 1 --email "founder@startup.com" --name "Jane Founder"
"""

import argparse
import sys
import json
from datetime import datetime
from app.core.database import SessionLocal
from app.services.executive_service import ExecutiveService
from app.services.annotation_service import AnnotationService
from app.services.relationship_service import RelationshipService


def list_executives(args):
    """List all executives."""
    db = SessionLocal()
    try:
        service = ExecutiveService(db)
        executives = service.list_executives(active_only=not args.all)

        if not executives:
            print("No executives found")
            return

        print(f"\n{'ID':<5} {'Name':<20} {'Email':<30} {'Active':<8} {'Calendars'}")
        print("-" * 100)

        for exec in executives:
            calendars = ", ".join(exec.google_calendar_ids or [])
            active = "Yes" if exec.is_active else "No"
            print(f"{exec.id:<5} {exec.name:<20} {exec.email:<30} {active:<8} {calendars}")

        print(f"\nTotal: {len(executives)} executive(s)")

    finally:
        db.close()


def create_executive(args):
    """Create a new executive."""
    db = SessionLocal()
    try:
        service = ExecutiveService(db)

        calendar_ids = args.calendar_ids.split(',') if args.calendar_ids else [args.email]

        executive = service.create_executive(
            name=args.name,
            email=args.email,
            google_calendar_ids=calendar_ids,
            title=args.title,
            timezone=args.timezone,
            delivery_time=args.delivery_time
        )

        print(f"\n✅ Created executive:")
        print(f"   ID: {executive.id}")
        print(f"   Name: {executive.name}")
        print(f"   Email: {executive.email}")
        print(f"   Calendar IDs: {executive.google_calendar_ids}")
        print(f"   Timezone: {executive.timezone}")
        print(f"   Delivery time: {executive.delivery_time}")

    finally:
        db.close()


def list_annotations(args):
    """List annotations for an executive."""
    db = SessionLocal()
    try:
        service = AnnotationService(db)
        annotations = service.list_annotations(
            args.executive_id,
            priority=args.priority,
            has_follow_up=args.follow_up
        )

        if not annotations:
            print(f"No annotations found for executive ID {args.executive_id}")
            return

        print(f"\n{'Event ID':<30} {'Priority':<10} {'Prep Notes'}")
        print("-" * 100)

        for ann in annotations:
            prep = (ann.prep_notes or "")[:50] + "..." if ann.prep_notes and len(ann.prep_notes) > 50 else (ann.prep_notes or "")
            print(f"{ann.event_id:<30} {ann.priority:<10} {prep}")

        print(f"\nTotal: {len(annotations)} annotation(s)")

    finally:
        db.close()


def create_annotation(args):
    """Create an annotation."""
    db = SessionLocal()
    try:
        service = AnnotationService(db)

        annotation = service.create_annotation(
            executive_id=args.executive_id,
            event_id=args.event_id,
            priority=args.priority,
            prep_notes=args.prep_notes,
            action_before_meeting=args.action
        )

        print(f"\n✅ Created annotation:")
        print(f"   Event ID: {annotation.event_id}")
        print(f"   Priority: {annotation.priority}")
        print(f"   Prep notes: {annotation.prep_notes[:50]}..." if annotation.prep_notes else "   No prep notes")

    finally:
        db.close()


def list_relationships(args):
    """List relationships for an executive."""
    db = SessionLocal()
    try:
        service = RelationshipService(db)
        relationships = service.list_relationships(
            args.executive_id,
            relationship_strength=args.strength,
            relationship_status=args.status
        )

        if not relationships:
            print(f"No relationships found for executive ID {args.executive_id}")
            return

        print(f"\n{'Name':<25} {'Email':<30} {'Strength':<12} {'Status':<15} {'Meetings'}")
        print("-" * 120)

        for rel in relationships:
            name = rel.person_name or "N/A"
            email = rel.person_email
            strength = rel.relationship_strength or "N/A"
            status = rel.relationship_status or "N/A"
            meetings = rel.total_meetings or 0
            print(f"{name:<25} {email:<30} {strength:<12} {status:<15} {meetings}")

        print(f"\nTotal: {len(relationships)} relationship(s)")

    finally:
        db.close()


def create_relationship(args):
    """Create a relationship."""
    db = SessionLocal()
    try:
        service = RelationshipService(db)

        relationship = service.create_or_update_relationship(
            executive_id=args.executive_id,
            person_email=args.email,
            person_name=args.name,
            person_company=args.company,
            relationship_strength=args.strength,
            relationship_status=args.status,
            relationship_notes=args.notes
        )

        print(f"\n✅ Created relationship:")
        print(f"   Person: {relationship.person_name} ({relationship.person_email})")
        print(f"   Company: {relationship.person_company or 'N/A'}")
        print(f"   Strength: {relationship.relationship_strength}")
        print(f"   Status: {relationship.relationship_status or 'N/A'}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="EA Mode CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Executives commands
    exec_parser = subparsers.add_parser("executives", help="Manage executives")
    exec_subparsers = exec_parser.add_subparsers(dest="subcommand")

    # executives list
    exec_list = exec_subparsers.add_parser("list", help="List all executives")
    exec_list.add_argument("--all", action="store_true", help="Include inactive executives")
    exec_list.set_defaults(func=list_executives)

    # executives create
    exec_create = exec_subparsers.add_parser("create", help="Create a new executive")
    exec_create.add_argument("--name", required=True, help="Executive name")
    exec_create.add_argument("--email", required=True, help="Executive email")
    exec_create.add_argument("--title", help="Executive title")
    exec_create.add_argument("--calendar-ids", help="Comma-separated calendar IDs (default: email)")
    exec_create.add_argument("--timezone", default="America/New_York", help="Timezone (default: America/New_York)")
    exec_create.add_argument("--delivery-time", default="08:00", help="Delivery time HH:MM (default: 08:00)")
    exec_create.set_defaults(func=create_executive)

    # Annotations commands
    ann_parser = subparsers.add_parser("annotations", help="Manage annotations")
    ann_subparsers = ann_parser.add_subparsers(dest="subcommand")

    # annotations list
    ann_list = ann_subparsers.add_parser("list", help="List annotations")
    ann_list.add_argument("--executive-id", type=int, required=True, help="Executive ID")
    ann_list.add_argument("--priority", help="Filter by priority")
    ann_list.add_argument("--follow-up", action="store_true", help="Only show annotations with follow-up")
    ann_list.set_defaults(func=list_annotations)

    # annotations create
    ann_create = ann_subparsers.add_parser("create", help="Create annotation")
    ann_create.add_argument("--executive-id", type=int, required=True, help="Executive ID")
    ann_create.add_argument("--event-id", required=True, help="Calendar event ID")
    ann_create.add_argument("--priority", default="normal", choices=["critical", "high", "normal", "low"], help="Priority level")
    ann_create.add_argument("--prep-notes", help="Prep notes for the meeting")
    ann_create.add_argument("--action", help="Action before meeting")
    ann_create.set_defaults(func=create_annotation)

    # Relationships commands
    rel_parser = subparsers.add_parser("relationships", help="Manage relationships")
    rel_subparsers = rel_parser.add_subparsers(dest="subcommand")

    # relationships list
    rel_list = rel_subparsers.add_parser("list", help="List relationships")
    rel_list.add_argument("--executive-id", type=int, required=True, help="Executive ID")
    rel_list.add_argument("--strength", help="Filter by strength (new, developing, strong, key)")
    rel_list.add_argument("--status", help="Filter by status (investor, founder, etc.)")
    rel_list.set_defaults(func=list_relationships)

    # relationships create
    rel_create = rel_subparsers.add_parser("create", help="Create relationship")
    rel_create.add_argument("--executive-id", type=int, required=True, help="Executive ID")
    rel_create.add_argument("--email", required=True, help="Person's email")
    rel_create.add_argument("--name", help="Person's name")
    rel_create.add_argument("--company", help="Person's company")
    rel_create.add_argument("--strength", default="new", choices=["new", "developing", "strong", "key"], help="Relationship strength")
    rel_create.add_argument("--status", help="Relationship status (investor, founder, etc.)")
    rel_create.add_argument("--notes", help="Relationship notes")
    rel_create.set_defaults(func=create_relationship)

    args = parser.parse_args()

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
