package compliance.authorization.user.verify.policy_0486

# Auto-generated policy 486 (Rego v1 syntax)
# Package: compliance.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0486",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0486_allowed if {
    input.user.role == "admin"
}
policy_0486_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0486_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
