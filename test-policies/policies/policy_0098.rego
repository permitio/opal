package risk.authentication.policy.verify.policy_0098

# Auto-generated policy 98 (Rego v1 syntax)
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0098",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0098_allowed if {
    input.user.active
    input.resource.public
}
policy_0098_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0098_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0098_allowed if {
    input.user.role == "admin"
}
