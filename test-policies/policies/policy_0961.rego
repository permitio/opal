package compliance.authentication.user.allow.policy_0961

# Auto-generated policy 961 (Rego v1 syntax)
# Package: compliance.authentication.user.allow

# Metadata
metadata := {
    "policy_id": "0961",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0961_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0961_allowed if {
    input.user.role == "admin"
}
