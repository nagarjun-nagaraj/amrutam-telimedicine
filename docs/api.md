# API Reference

Base URL: `http://localhost:8000/api/v1`

Interactive docs: **http://localhost:8000/docs**

---

## Authentication

### Register
```
POST /auth/register
{
  "email": "user@example.com",
  "password": "Test@1234",
  "first_name": "John",
  "last_name": "Doe",
  "role": "patient"
}
→ 201: {id, email, role, created_at}
```

### Login
```
POST /auth/login
{
  "email": "user@example.com",
  "password": "Test@1234"
}
→ 200: {access_token, refresh_token, user_id, role}
```

### Get Current User
```
GET /auth/me
Authorization: Bearer {token}
→ 200: {id, email, role, is_active}
```

---

## Doctors

### Search Doctors
```
GET /doctors?specialization=Cardiology&page=1
→ 200: {items: [...], total, page, page_size}
```

### Create Doctor Profile
```
POST /doctors
Authorization: Bearer {token}
{
  "license_number": "MH-12345",
  "specialization": "Cardiology",
  "consultation_fee": 500.00
}
→ 201: {id, user_id, specialization, is_verified}
```

### Create Availability Slot
```
POST /doctors/{id}/slots
Authorization: Bearer {token}
{
  "start_time": "2026-02-20T10:00:00Z",
  "end_time": "2026-02-20T10:30:00Z"
}
→ 201: {id, doctor_id, start_time, status}
```

---

## Consultations

### Book Consultation
```
POST /consultations
Authorization: Bearer {token}
{
  "doctor_id": "uuid",
  "slot_id": "uuid",
  "chief_complaint": "Chest pain",
  "idempotency_key": "booking-123"
}
→ 201: {id, status, meeting_url}
```

### Create Prescription
```
POST /consultations/{id}/prescriptions
Authorization: Bearer {token} (Doctor only)
{
  "medications": [{"name": "Aspirin", "dosage": "75mg"}],
  "instructions": "Take after meals"
}
→ 201: {id, consultation_id, medications}
```

### Process Payment
```
POST /consultations/{id}/payments
Authorization: Bearer {token}
{
  "payment_gateway": "razorpay",
  "idempotency_key": "payment-123"
}
→ 200: {id, amount, status, gateway_transaction_id}
```

---

## Admin

### Analytics
```
GET /admin/analytics
Authorization: Bearer {token} (Admin only)
→ 200: {total_users, total_consultations, revenue_today}
```

### Audit Logs
```
GET /admin/audit-logs?action=consultation_booked
Authorization: Bearer {token} (Admin only)
→ 200: {items: [...], total}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 409 | Conflict (duplicate/already booked) |
| 422 | Validation Error |
| 429 | Rate Limit Exceeded |