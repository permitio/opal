package access.enforcement.user.check.policy_0600

# Auto-generated policy 600 (Rego v1 syntax)
# Package: access.enforcement.user.check

# Metadata
metadata := {
    "policy_id": "0600",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0600_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0600_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
