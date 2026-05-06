package security.authentication.policy.check.policy_0120

# Auto-generated policy 120 (Rego v1 syntax)
# Package: security.authentication.policy.check

# Metadata
metadata := {
    "policy_id": "0120",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0120_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0120_allowed if {
    input.user.role == "admin"
}
policy_0120_allowed if {
    input.user.active
    input.resource.public
}
policy_0120_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
