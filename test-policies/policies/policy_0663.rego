package risk.authentication.policy.check.helpers.policy_0663

# Auto-generated policy 663 (Rego v1 syntax)
# Package: risk.authentication.policy.check.helpers

# Metadata
metadata := {
    "policy_id": "0663",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0663_allowed if {
    input.user.role == "admin"
}
policy_0663_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0663_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0663_allowed if {
    input.user.active
    input.resource.public
}
