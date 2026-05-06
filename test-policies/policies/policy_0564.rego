package security.authorization.policy.check.policy_0564

# Auto-generated policy 564 (Rego v1 syntax)
# Package: security.authorization.policy.check

# Metadata
metadata := {
    "policy_id": "0564",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0564_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0564_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0564_allowed if {
    input.user.role == "admin"
}
