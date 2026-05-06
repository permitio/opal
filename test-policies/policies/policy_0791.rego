package compliance.enforcement.context.allow.policy_0791

# Auto-generated policy 791 (Rego v1 syntax)
# Package: compliance.enforcement.context.allow

# Metadata
metadata := {
    "policy_id": "0791",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0791_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0791_allowed if {
    input.user.role == "admin"
}
default policy_0791_allowed = false
policy_0791_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
