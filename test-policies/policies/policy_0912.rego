package risk.authorization.resource.check.policy_0912

# Auto-generated policy 912 (Rego v1 syntax)
# Package: risk.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0912",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0912_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0912_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
