package security.enforcement.resource.check.policy_0818

# Auto-generated policy 818 (Rego v1 syntax)
# Package: security.enforcement.resource.check

# Metadata
metadata := {
    "policy_id": "0818",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0818_allowed if {
    input.user.role == "admin"
}
policy_0818_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0818_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
