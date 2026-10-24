"""Explicitly opt-in fictional demo records. Never run against real data."""
from .services import local_today
from sqlalchemy import select
from .main import initialize
from .db import SessionLocal
from .models import User, Room, Resident
from .security import hashing

def main():
    initialize()
    with SessionLocal() as db:
        if db.scalar(select(Room.id)) or db.scalar(select(Resident.id)):
            print('Demo seed skipped: rooms or residents already exist.'); return
        rooms=[Room(number='101',floor='Ground',capacity=1,monthly_fee=12000),
               Room(number='102',floor='Ground',capacity=2,monthly_fee=8500),
               Room(number='201',floor='First',capacity=3,monthly_fee=6500),
               Room(number='202',floor='First',capacity=3,monthly_fee=6500)]
        db.add_all(rooms); db.flush()
        for name,email,room,discount in [('Aarav Demo','aarav@example.com',rooms[1],500),('Maya Demo','maya@example.com',rooms[2],0),('Dev Demo','dev@example.com',rooms[2],250)]:
            u=User(email=email,password_hash=hashing.hash('ResidentDemo123!'),role='resident',must_change_password=True)
            db.add(u); db.flush()
            db.add(Resident(user_id=u.id,name=name,phone='9000000000',guardian='Demo guardian',institution='Demo Institute',joined_on=local_today().replace(day=1),room_id=room.id,discount=discount,aadhaar_last4='0000'))
        db.commit()
        print('Fictional demo data created. Resident login: aarav@example.com / ResidentDemo123!')
if __name__=='__main__': main()
